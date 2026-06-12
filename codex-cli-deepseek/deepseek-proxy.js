/**
 * deepseek-proxy.js
 * Translates OpenAI Responses API (/v1/responses) → DeepSeek chat completions (/v1/chat/completions)
 * Also serves /v1/models in Codex-compatible format for /model switching.
 */

const http  = require('http');
const https = require('https');

// ── Debug mode ────────────────────────────────────────────────────────────────
const DEBUG = process.argv.includes('--debug') ||
              process.env.PROXY_DEBUG === 'true' ||
              process.env.DEBUG === 'true';

function log(...args)   { if (DEBUG) console.log(...args); }

const PORT             = parseInt(process.env.PROXY_PORT || '3333', 10);
const DEEPSEEK_HOST    = 'api.deepseek.com';
const DEEPSEEK_PATH    = '/v1/chat/completions';
const DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY;

// Reuse TLS connections across requests
const httpsAgent = new https.Agent({ keepAlive: true, maxSockets: 4 });

if (!DEEPSEEK_API_KEY) {
  console.error('[codex-proxy] ERROR: DEEPSEEK_API_KEY not set.');
  process.exit(1);
}

// ── Stats ────────────────────────────────────────────────────────────────────
const stats = { requests: 0, inputTokens: 0, outputTokens: 0, errors: 0, start: Date.now() };

function printStats() {
  const elapsed = ((Date.now() - stats.start) / 1000).toFixed(0);
  console.log(`\n[codex-proxy] ── Session stats (${elapsed}s) ──`);
  console.log(`  Requests:      ${stats.requests}`);
  console.log(`  Input tokens:  ${stats.inputTokens}`);
  console.log(`  Output tokens: ${stats.outputTokens}`);
  console.log(`  Total tokens:  ${stats.inputTokens + stats.outputTokens}`);
  console.log(`  Errors:        ${stats.errors}`);
  console.log(`  Avg in/req:    ${stats.requests ? Math.round(stats.inputTokens / stats.requests) : 0}`);
  console.log(`  Avg out/req:   ${stats.requests ? Math.round(stats.outputTokens / stats.requests) : 0}`);
}

process.on('SIGINT',  () => { printStats(); process.exit(); });
process.on('SIGTERM', () => { printStats(); process.exit(); });

// ── Model registry ──────────────────────────────────────────────────────────
const CODEX_MODEL_TEMPLATE = {
  supported_reasoning_levels: [
    { effort: 'low',    description: 'Fast responses with lighter reasoning' },
    { effort: 'medium', description: 'Balances speed and reasoning depth for everyday tasks' },
    { effort: 'high',   description: 'Greater reasoning depth for complex problems' },
  ],
  shell_type:                     'shell_command',
  visibility:                     'list',
  supported_in_api:               true,
  priority:                       0,
  additional_speed_tiers:         [],
  supports_reasoning_summaries:   true,
  default_reasoning_summary:      'none',
  support_verbosity:              true,
  default_verbosity:              'low',
  apply_patch_tool_type:          'freeform',
  web_search_tool_type:           'text_and_image',
  truncation_policy:              { mode: 'tokens', limit: 10000 },
  supports_parallel_tool_calls:   true,
  supports_image_detail_original: false,
  effective_context_window_percent: 95,
  experimental_supported_tools:   [],
  input_modalities:               ['text'],
  supports_search_tool:           true,
};

const DEEPSEEK_MODELS = [
  {
    slug:                  'gpt-5.4',
    display_name:          'DeepSeek V4 Pro',
    description:           'Most capable DeepSeek model — complex coding, research, and real-world work.',
    default_reasoning_level: 'high',
    context_window:        131072,
    max_context_window:    131072,
    ...CODEX_MODEL_TEMPLATE,
  },
  {
    slug:                  'gpt-5.5',
    display_name:          'DeepSeek V4 Pro',
    description:           'Most capable DeepSeek model — complex coding, research, and real-world work.',
    default_reasoning_level: 'xhigh',
    context_window:        131072,
    max_context_window:    131072,
    ...CODEX_MODEL_TEMPLATE,
  },
  {
    slug:                  'gpt-5.4-mini',
    display_name:          'DeepSeek V4 Flash',
    description:           'Fast, economical DeepSeek model for everyday coding.',
    default_reasoning_level: 'medium',
    context_window:        131072,
    max_context_window:    131072,
    ...CODEX_MODEL_TEMPLATE,
  },
];

const MODEL_BY_SLUG = {};
for (const m of DEEPSEEK_MODELS) MODEL_BY_SLUG[m.slug] = m;

// ── reasoning_content preservation ───────────────────────────────────────────
let lastReasoningContent = '';

// ── Model name mapping ──────────────────────────────────────────────────────
const MODEL_MAP = {
  'deepseek-v4-flash':  'deepseek-v4-flash',
  'deepseek-v4-pro':    'deepseek-v4-pro',
  'gpt-5.4-mini':       'deepseek-v4-flash',
  'gpt-5.3-codex':      'deepseek-v4-flash',
  'gpt-5.2':            'deepseek-v4-flash',
  'gpt-5.5':            'deepseek-v4-pro',
  'gpt-5.4':            'deepseek-v4-pro',
};

const DEFAULT_DEEPSEEK_MODEL = 'deepseek-v4-flash';

function resolveModel(codexModel) {
  if (MODEL_MAP[codexModel]) return MODEL_MAP[codexModel];
  if (codexModel && codexModel.startsWith('gpt-')) return DEFAULT_DEEPSEEK_MODEL;
  return codexModel ?? DEFAULT_DEEPSEEK_MODEL;
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function uid(prefix = 'id') {
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

function json(res, status, obj) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(obj));
}

// ── Protocol conversion: Responses API → chat completions ────────────────────
function convertInput(input, reasoningContent = '') {
  const messages = [];

  if (typeof input === 'string') {
    messages.push({ role: 'user', content: input });
    return messages;
  }

  if (!Array.isArray(input)) return messages;

  for (let i = 0; i < input.length; i++) {
    const item = input[i];

    if (item.type === 'message') {
      let content = item.content;
      if (Array.isArray(content)) {
        content = content
          .map(c => {
            if (typeof c === 'string')                                     return c;
            if (c.type === 'text' || c.type === 'output_text')             return c.text ?? '';
            if (c.type === 'input_text')                                   return c.text ?? '';
            if (c.type === 'refusal')                                      return c.refusal ?? '';
            return '';
          })
          .join('');
      }
      const role = item.role === 'developer' ? 'system' : item.role;
      messages.push({ role, content: content ?? '' });

    } else if (item.type === 'function_call') {
      const tool_calls = [];
      while (i < input.length && input[i].type === 'function_call') {
        const fc = input[i];
        tool_calls.push({
          id:       fc.call_id ?? fc.id ?? uid('call'),
          type:     'function',
          function: { name: fc.name, arguments: fc.arguments ?? '{}' }
        });
        i++;
      }
      i--;
      const msg = { role: 'assistant', content: null, tool_calls };
      if (reasoningContent) {
        msg.reasoning_content = reasoningContent;
      }
      messages.push(msg);

    } else if (item.type === 'function_call_output') {
      messages.push({
        role:         'tool',
        tool_call_id: item.call_id,
        content:      typeof item.output === 'string' ? item.output : JSON.stringify(item.output ?? '')
      });
    }
  }

  return messages;
}

function convertTools(tools) {
  if (!Array.isArray(tools) || tools.length === 0) return undefined;
  const out = tools
    .filter(t => t.type === 'function')
    .map(t => ({
      type:     'function',
      function: { name: t.name, description: t.description ?? '', parameters: t.parameters ?? {} }
    }));
  return out.length > 0 ? out : undefined;
}

function buildChatRequest(body, reasoningContent = '') {
  const messages = convertInput(body.input, reasoningContent);

  if (body.instructions) {
    messages.unshift({ role: 'system', content: body.instructions });
  }

  const req = {
    model:    resolveModel(body.model),
    messages,
    stream:   true,
  };
  const tools = convertTools(body.tools);
  if (tools)                    req.tools        = tools;
  if (body.tool_choice != null) req.tool_choice  = body.tool_choice;
  if (body.temperature != null) req.temperature  = body.temperature;
  if (body.max_output_tokens)   req.max_tokens   = body.max_output_tokens;
  return req;
}

// ── Protocol conversion: chat completions stream → Responses API SSE ─────────
function sse(res, event) {
  res.write(`data: ${JSON.stringify(event)}\n\n`);
}

async function pipeStream(deepseekRes, clientRes, responseId) {
  const msgId   = uid('msg');
  let textBuf   = '';
  let partOpen  = false;
  let itemOpen  = false;
  const toolMap = {};
  let rawBuf       = Buffer.alloc(0);
  let reasoningBuf = '';
  let streamUsage  = null;

  deepseekRes.on('data', chunk => { rawBuf = Buffer.concat([rawBuf, chunk]); processBuffer(); });
  deepseekRes.on('end', () => {
    if (rawBuf.length > 0) {
      rawBuf = Buffer.concat([rawBuf, Buffer.from('\n')]);
      processBuffer();
    }
    if (reasoningBuf) {
      lastReasoningContent = reasoningBuf;
      log(`[codex-proxy] captured reasoning_content (${reasoningBuf.length} chars)`);
    }
    if (streamUsage) {
      stats.inputTokens  += streamUsage.prompt_tokens     ?? 0;
      stats.outputTokens += streamUsage.completion_tokens ?? 0;
      log(`[codex-proxy] done | in:${stats.inputTokens} out:${stats.outputTokens} total:${stats.inputTokens + stats.outputTokens}`);
    }
    finalise();
  });
  deepseekRes.on('error', err => {
    log('[codex-proxy] upstream error:', err.message);
    clientRes.end();
  });

  function processBuffer() {
    const str   = rawBuf.toString();
    const lines = str.split('\n');
    rawBuf = Buffer.from(lines.pop());
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed === 'data: [DONE]') continue;
      if (!trimmed.startsWith('data:')) continue;
      try {
        const parsed = JSON.parse(trimmed.slice(5).trim());
        handleChunk(parsed);
      } catch { /* skip malformed */ }
    }
  }

  function handleChunk(chunk) {
    if (chunk.usage) streamUsage = chunk.usage;

    const choice = chunk.choices?.[0];
    if (!choice) return;
    const delta = choice.delta ?? {};

    if (delta.reasoning_content) {
      reasoningBuf += delta.reasoning_content;
    }

    if (delta.content) {
      if (!itemOpen) {
        itemOpen = true;
        sse(clientRes, {
          type: 'response.output_item.added',
          response_id: responseId, output_index: 0,
          item: { type: 'message', id: msgId, role: 'assistant', content: [], status: 'in_progress' }
        });
      }
      if (!partOpen) {
        partOpen = true;
        sse(clientRes, {
          type: 'response.content_part.added',
          response_id: responseId, item_id: msgId, output_index: 0, content_index: 0,
          part: { type: 'output_text', text: '' }
        });
      }
      textBuf += delta.content;
      sse(clientRes, {
        type: 'response.output_text.delta',
        response_id: responseId, item_id: msgId, output_index: 0, content_index: 0,
        delta: delta.content
      });
    }

    if (delta.tool_calls) {
      for (const tc of delta.tool_calls) {
        const idx = tc.index ?? 0;
        if (!toolMap[idx]) {
          const callId = tc.id ?? uid('call');
          const fcId   = uid('fc');
          toolMap[idx] = { callId, name: '', argsBuf: '', fcId };
          sse(clientRes, {
            type: 'response.output_item.added',
            response_id: responseId, output_index: idx,
            item: { type: 'function_call', id: fcId, call_id: callId, name: '', arguments: '', status: 'in_progress' }
          });
        }
        if (tc.function?.name)      toolMap[idx].name    += tc.function.name;
        if (tc.function?.arguments) {
          toolMap[idx].argsBuf += tc.function.arguments;
          sse(clientRes, {
            type: 'response.function_call_arguments.delta',
            response_id: responseId, item_id: toolMap[idx].fcId, output_index: idx,
            delta: tc.function.arguments
          });
        }
      }
    }
  }

  function finalise() {
    if (partOpen) {
      sse(clientRes, { type: 'response.output_text.done',    response_id: responseId, item_id: msgId, output_index: 0, content_index: 0, text: textBuf });
      sse(clientRes, { type: 'response.content_part.done',   response_id: responseId, item_id: msgId, output_index: 0, content_index: 0, part: { type: 'output_text', text: textBuf } });
      sse(clientRes, { type: 'response.output_item.done',    response_id: responseId, output_index: 0, item: { type: 'message', id: msgId, role: 'assistant', content: [{ type: 'output_text', text: textBuf }], status: 'completed' } });
    }

    const outputItems = partOpen
      ? [{ type: 'message', id: msgId, role: 'assistant', content: [{ type: 'output_text', text: textBuf }], status: 'completed' }]
      : [];

    for (const [idxStr, tc] of Object.entries(toolMap)) {
      const idx = parseInt(idxStr, 10);
      sse(clientRes, { type: 'response.function_call_arguments.done', response_id: responseId, item_id: tc.fcId, output_index: idx, arguments: tc.argsBuf });
      sse(clientRes, { type: 'response.output_item.done', response_id: responseId, output_index: idx, item: { type: 'function_call', id: tc.fcId, call_id: tc.callId, name: tc.name, arguments: tc.argsBuf, status: 'completed' } });
      outputItems.push({ type: 'function_call', id: tc.fcId, call_id: tc.callId, name: tc.name, arguments: tc.argsBuf, status: 'completed' });
    }

    const hasToolCalls = Object.keys(toolMap).length > 0;
    const usage = {
      input_tokens:  streamUsage?.prompt_tokens     ?? 0,
      output_tokens: streamUsage?.completion_tokens ?? 0,
      total_tokens:  streamUsage?.total_tokens      ?? 0,
    };
    sse(clientRes, {
      type: 'response.completed',
      response: {
        id: responseId, object: 'response',
        created_at: Math.floor(Date.now() / 1000),
        status: hasToolCalls ? 'requires_action' : 'completed',
        output: outputItems,
        usage,
      }
    });
    sse(clientRes, {
      type: 'response.done',
      response: {
        id: responseId, object: 'response',
        created_at: Math.floor(Date.now() / 1000),
        status: hasToolCalls ? 'requires_action' : 'completed',
        output: outputItems,
        usage,
      }
    });

    clientRes.write('data: [DONE]\n\n');
    clientRes.end();
  }
}

// ── HTTP server ───────────────────────────────────────────────────────────────
const server = http.createServer((req, clientRes) => {
  const method = req.method;
  const url    = req.url;

  log(`[codex-proxy] ${method} ${url}`);

  // ── GET /health ────────────────────────────────────────────────────────────
  if (method === 'GET' && url === '/health') {
    return json(clientRes, 200, { status: 'ok', proxy: 'codex-proxy', stats });
  }

  // ── GET /stats ─────────────────────────────────────────────────────────────
  if (method === 'GET' && url === '/stats') {
    return json(clientRes, 200, stats);
  }

  // ── GET /v1/models ─────────────────────────────────────────────────────────
  if (method === 'GET' && (url === '/v1/models' || url === '/models' || url.startsWith('/models?'))) {
    const clientVersion = (url.match(/client_version=([^&]+)/) || [])[1] || '0.0.0';
    return json(clientRes, 200, {
      fetched_at:     new Date().toISOString(),
      etag:           `deepseek-proxy-${Date.now()}`,
      client_version: clientVersion,
      models:         DEEPSEEK_MODELS,
    });
  }

  // ── GET /v1/models/:id ─────────────────────────────────────────────────────
  const modelMatch = url.match(/^\/v1\/models\/([^?]+)/) || url.match(/^\/models\/([^?]+)/);
  if (method === 'GET' && modelMatch) {
    const modelId = modelMatch[1];
    const model = MODEL_BY_SLUG[modelId];
    if (model) return json(clientRes, 200, model);
    return json(clientRes, 404, { error: { message: `Model '${modelId}' not found`, type: 'invalid_request_error' } });
  }

  // ── POST /v1/responses ─────────────────────────────────────────────────────
  if (method === 'POST' && (url.startsWith('/v1/responses') || url.startsWith('/responses'))) {
    const chunks = [];
    req.on('data', chunk => { chunks.push(chunk); });
    req.on('end', () => {
      let parsed;
      try { parsed = JSON.parse(Buffer.concat(chunks).toString()); }
      catch {
        return json(clientRes, 400, { error: 'Invalid JSON' });
      }

      const reasoningContent = lastReasoningContent;
      const chatBody   = buildChatRequest(parsed, reasoningContent);
      const responseId = uid('resp');
      const postData   = JSON.stringify(chatBody);

      stats.requests++;
      log(`[codex-proxy] → ${chatBody.model} | stream:true | max_tokens:${chatBody.max_tokens ?? '?'} | messages:${chatBody.messages.length} | tools:${chatBody.tools?.length ?? 0}`);

      const options = {
        hostname: DEEPSEEK_HOST,
        port:     443,
        path:     DEEPSEEK_PATH,
        method:   'POST',
        agent:    httpsAgent,
        headers:  {
          'Content-Type':   'application/json',
          'Content-Length': Buffer.byteLength(postData),
          'Authorization':  `Bearer ${DEEPSEEK_API_KEY}`,
        }
      };

      clientRes.writeHead(200, {
        'Content-Type':  'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection':    'keep-alive',
      });

      sse(clientRes, {
        type: 'response.created',
        response: { id: responseId, object: 'response', created_at: Math.floor(Date.now() / 1000), status: 'in_progress', output: [] }
      });

      const upstreamReq = https.request(options, upstreamRes => {
        if (upstreamRes.statusCode !== 200) {
          stats.errors++;
          let errBody = '';
          upstreamRes.on('data', d => { errBody += d; });
          upstreamRes.on('end', () => {
            log(`[codex-proxy] ERROR ${upstreamRes.statusCode}: ${errBody.slice(0, 300)}`);
            sse(clientRes, { type: 'response.done', response: { id: responseId, status: 'failed', error: { code: 'upstream_error', message: errBody } } });
            clientRes.end();
          });
          return;
        }
        pipeStream(upstreamRes, clientRes, responseId);
      });

      upstreamReq.on('error', err => {
        stats.errors++;
        log(`[codex-proxy] upstream error: ${err.message}`);
        sse(clientRes, { type: 'response.done', response: { id: responseId, status: 'failed', error: { code: 'proxy_error', message: err.message } } });
        clientRes.end();
      });

      upstreamReq.write(postData);
      upstreamReq.end();
    });
    return;
  }

  // ── Everything else ────────────────────────────────────────────────────────
  json(clientRes, 404, { error: `Not found: ${method} ${url}` });
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`\n  ╔══════════════════════════════════════════════╗`);
  console.log(`  ║      Codex Switch Proxy for DeepSeek        ║`);
  console.log(`  ╠══════════════════════════════════════════════╣`);
  console.log(`  ║  Proxy:  http://127.0.0.1:${PORT}                      ║`);
  console.log(`  ║  Backend: DeepSeek (${DEEPSEEK_HOST})            ║`);
  console.log(`  ║  Debug:  ${DEBUG ? 'ON' : 'OFF'}                                  ║`);
  console.log(`  ║  Stats:  http://127.0.0.1:${PORT}/stats              ║`);
  console.log(`  ╚══════════════════════════════════════════════╝`);
  console.log(`  Press Ctrl+C for session summary\n`);
});
