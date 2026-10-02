import { createServer } from "node:http";
import { localBrowser, Stagehand } from "@browserbasehq/stagehand";
import { z } from "zod/v4";
import OpenAI from "openai";

const PORT = parseInt(process.env.STAGEHAND_PORT || "8931", 10);
const CHROME_PATH = process.env.CHROME_PATH || "/usr/bin/google-chrome-stable";
const PROXY_HOST = process.env.PROXY_HOST || "proxy-web";
const PROXY_PORT = process.env.PROXY_PORT || "8888";
const LITELLM_URL = process.env.LITELLM_URL || "http://litellm:4000/v1";
const LITELLM_API_KEY = process.env.LITELLM_MASTER_KEY || "";
const MODEL = process.env.STAGEHAND_MODEL || "deepseek-flash";
const OTLP_ENDPOINT = process.env.OTEL_EXPORTER_OTLP_ENDPOINT || "";

const litellm = new OpenAI({
  apiKey: LITELLM_API_KEY || "sk-local",
  baseURL: LITELLM_URL,
});

// Stagehand v4 BYO-LLM callback -> LiteLLM (OpenAI-compatible chat.completions).
// Uses JSON-object mode (works with DeepSeek) and injects the schema into the
// system prompt so the model returns valid structured JSON.
async function generate(params) {
  const rf = params.responseFormat || {};
  let systemPrompt = params.systemPrompt || "";
  if (rf.type === "json_schema" && rf.schema) {
    systemPrompt +=
      "\nRespond with valid JSON only, matching this JSON schema:\n" +
      JSON.stringify(rf.schema);
  }
  const messages = [
    ...(systemPrompt ? [{ role: "system", content: systemPrompt }] : []),
    ...(params.messages || []).map((m) => ({
      role: m.role,
      content: typeof m.content === "string" ? m.content : JSON.stringify(m.content),
    })),
  ];
  const res = await litellm.chat.completions.create({
    model: MODEL,
    messages,
    temperature: params.temperature ?? 0,
    response_format: { type: "json_object" },
  });
  const text = res.choices?.[0]?.message?.content ?? "";
  let structuredContent = null;
  try {
    structuredContent = JSON.parse(text);
  } catch {
    structuredContent = text;
  }
  return {
    role: "assistant",
    content: { type: "text", text },
    outputFormat: "json_schema",
    structuredContent,
  };
}

let browser;
let stagehand;
let page;

async function init() {
  browser = await localBrowser.launch({
    executablePath: CHROME_PATH,
    port: 9222,
    userDataDir: "/browser-profile/anon",
    headless: false,
    chromiumSandbox: false,
    locale: "en-US",
  });
  stagehand = await Stagehand.create({
    browser,
    model: { generate },
    ...(OTLP_ENDPOINT
      ? { telemetry: { traces: { endpoint: OTLP_ENDPOINT } } }
      : {}),
  });
  const pages = await browser.context.pages();
  page = pages[0] || (await browser.context.newPage());
  return { ok: true };
}

function json(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => {
      if (!data) return resolve({});
      try {
        resolve(JSON.parse(data));
      } catch (e) {
        reject(e);
      }
    });
    req.on("error", reject);
  });
}

// Minimal JSON-schema -> zod builder for extract(). Supports object fields of
// string/number/boolean and arrays of strings/objects.
function buildSchema(spec) {
  const root = spec || {};
  const make = (node) => {
    const t = node.type || "string";
    switch (t) {
      case "string":
        return z.string();
      case "number":
        return z.number();
      case "boolean":
        return z.boolean();
      case "array":
        if (node.items) return z.array(make(node.items));
        return z.array(z.string());
      case "object": {
        const shape = {};
        for (const [k, v] of Object.entries(node.properties || {})) shape[k] = make(v);
        return z.object(shape);
      }
      default:
        return z.string();
    }
  };
  return make(root);
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  const path = url.pathname;

  if (req.method === "GET" && path === "/healthz") {
    return json(res, 200, { ok: true, ready: !!stagehand });
  }

  let body;
  try {
    body = await readBody(req);
  } catch {
    return json(res, 400, { error: "invalid json body" });
  }

  try {
    if (req.method === "POST" && path === "/navigate") {
      if (!body.url) return json(res, 400, { error: "url required" });
      await page.goto(body.url, { waitUntil: "domcontentloaded", timeout: 60000 });
      return json(res, 200, { ok: true, url: String(page.url()), title: await page.title() });
    }

    if (req.method === "POST" && path === "/read") {
      const text = await page.locator("body").innerText({ timeout: 30000 }).catch(() => "");
      return json(res, 200, { text });
    }

    if (req.method === "POST" && path === "/act") {
      if (!body.instruction) return json(res, 400, { error: "instruction required" });
      const result = await stagehand.act(body.instruction);
      return json(res, 200, { ok: true, result: result?.message ?? null });
    }

    if (req.method === "POST" && path === "/observe") {
      if (!body.instruction) return json(res, 400, { error: "instruction required" });
      const { data } = await stagehand.observe(body.instruction);
      return json(res, 200, { data });
    }

    if (req.method === "POST" && path === "/extract") {
      if (!body.instruction) return json(res, 400, { error: "instruction required" });
      const schema = buildSchema(body.schema);
      const { data } = await stagehand.extract(body.instruction, schema);
      return json(res, 200, { data });
    }

    if (req.method === "POST" && path === "/screenshot") {
      const buf = await page.screenshot({ fullPage: !!body.fullPage });
      return json(res, 200, { screenshot: buf.toString("base64") });
    }

    return json(res, 404, { error: "unknown endpoint" });
  } catch (e) {
    return json(res, 500, { error: String(e?.message || e) });
  }
});

init()
  .then(() => {
    server.listen(PORT, "0.0.0.0", () => {
      console.log(`stagehand service listening on :${PORT}`);
    });
  })
  .catch((e) => {
    console.error("FATAL: stagehand init failed", e);
    process.exit(1);
  });
