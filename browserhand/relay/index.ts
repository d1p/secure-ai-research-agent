import { randomBytes, timingSafeEqual } from "node:crypto";
import {
  createServer,
  type IncomingMessage,
  type ServerResponse,
} from "node:http";
import { WebSocketServer, WebSocket } from "ws";

// ── Config ───────────────────────────────────────────────────────

const PORT = Number(process.env.BROWSERHAND_PORT) || 29981;
const HOST = process.env.BROWSERHAND_HOST || "127.0.0.1";
const COMMAND_TIMEOUT_MS = 30_000;
const MULTI_USER = process.env.BROWSERHAND_MODE === "multi";
const API_KEY = process.env.BROWSERHAND_API_KEY || "";

// Require a token on /command even in local mode. Off by default so local
// usage stays zero-config; set BROWSERHAND_REQUIRE_AUTH=1 to harden.
const REQUIRE_LOCAL_AUTH =
  process.env.BROWSERHAND_REQUIRE_AUTH === "1" ||
  process.env.BROWSERHAND_REQUIRE_AUTH === "true";

// Optionally pin the extension's id for the WebSocket Origin check.
const EXTENSION_ID = process.env.BROWSERHAND_EXTENSION_ID || "";

// Manual token: for non-extension clients in local mode (testing, scripts)
const MANUAL_TOKEN =
  process.env.BROWSERHAND_TOKEN || randomBytes(32).toString("base64url");

// ── State ────────────────────────────────────────────────────────

// Single-user mode: one extension connection
let singleSocket: WebSocket | null = null;

// Multi-user mode: userId → WebSocket
const userSockets = new Map<string, WebSocket>();

interface PendingRequest {
  resolve: (result: unknown) => void;
  timer: ReturnType<typeof setTimeout>;
  userId: string;
}
const pendingRequests = new Map<string, PendingRequest>();

// ── Debug log (ring buffer, last 100 entries) ────────────────────

interface LogEntry {
  time: string;
  direction: "→ ext" | "← ext" | "→ tool" | "← tool" | "system";
  summary: string;
  detail?: unknown;
}
const debugLog: LogEntry[] = [];
const MAX_LOG = 100;

function addLog(
  direction: LogEntry["direction"],
  summary: string,
  detail?: unknown,
) {
  const entry: LogEntry = {
    time: new Date().toISOString().slice(11, 23),
    direction,
    summary,
    detail,
  };
  debugLog.push(entry);
  if (debugLog.length > MAX_LOG) debugLog.shift();
  console.log(`[browserhand] ${entry.time} ${direction} ${summary}`);
}

// ── Auth ─────────────────────────────────────────────────────────

function isValidManualToken(candidate: string): boolean {
  try {
    const a = new Uint8Array(Buffer.from(MANUAL_TOKEN));
    const b = new Uint8Array(Buffer.from(candidate));
    if (a.length !== b.length) return false;
    return timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

function isValidApiKey(candidate: string): boolean {
  if (!API_KEY) return true; // No API key configured = no check
  try {
    const a = new Uint8Array(Buffer.from(API_KEY));
    const b = new Uint8Array(Buffer.from(candidate));
    if (a.length !== b.length) return false;
    return timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

// A real chrome-extension:// origin is exactly the scheme + a 32-char id with
// no path or port. Exact-match it (and optionally pin a specific id) so a
// spoofed origin like chrome-extension://evil.example.com cannot pass.
function isTrustedExtensionOrigin(origin: string): boolean {
  const prefix = "chrome-extension://";
  if (!origin.startsWith(prefix)) return false;
  const id = origin.slice(prefix.length);
  if (!/^[a-p]{32}$/.test(id)) return false;
  return EXTENSION_ID ? id === EXTENSION_ID : true;
}

function authenticateUpgrade(
  req: IncomingMessage,
): { ok: true; userId: string } | { ok: false } {
  const url = new URL(req.url || "/", `http://${HOST}:${PORT}`);
  const origin = req.headers.origin || "";
  const token = url.searchParams.get("token") || "";
  const userId = url.searchParams.get("userId") || "default";

  // Local mode: a well-formed chrome-extension:// origin is trusted
  if (isTrustedExtensionOrigin(origin)) {
    return { ok: true, userId };
  }

  // Token auth (local manual token or cloud token)
  if (token && isValidManualToken(token)) {
    return { ok: true, userId };
  }

  return { ok: false };
}

// ── Connection helpers ──────────────────────────────────────────

function getSocket(userId?: string): WebSocket | null {
  if (MULTI_USER) {
    const id = userId || "default";
    const ws = userSockets.get(id);
    return ws && ws.readyState === WebSocket.OPEN ? ws : null;
  }
  return singleSocket && singleSocket.readyState === WebSocket.OPEN
    ? singleSocket
    : null;
}

function setSocket(userId: string, ws: WebSocket): void {
  if (MULTI_USER) {
    const existing = userSockets.get(userId);
    if (existing && existing !== ws) {
      existing.close();
    }
    userSockets.set(userId, ws);
  } else {
    if (singleSocket && singleSocket !== ws) {
      singleSocket.close();
    }
    singleSocket = ws;
  }
}

function removeSocket(userId: string, ws: WebSocket): void {
  if (MULTI_USER) {
    if (userSockets.get(userId) === ws) {
      userSockets.delete(userId);
    }
  } else {
    if (singleSocket === ws) {
      singleSocket = null;
    }
  }
}

// ── HTTP server ──────────────────────────────────────────────────

function authenticateCommand(req: IncomingMessage): boolean {
  const auth = req.headers.authorization || "";
  const bearer = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (API_KEY) return isValidApiKey(bearer);
  if (REQUIRE_LOCAL_AUTH) return isValidManualToken(bearer);
  return true; // zero-config local mode: no token required
}

// Reject requests whose Host header is not a loopback name. On a DNS-rebinding
// attack the browser sends the attacker's hostname here, not localhost, so this
// is the load-bearing anti-rebinding check (per the MCP spec and rmcp fix).
function isAllowedHost(req: IncomingMessage): boolean {
  if (HOST !== "127.0.0.1") return true; // cloud mode is fronted by a proxy
  const host = (req.headers.host || "").toLowerCase();
  const hostname = host.startsWith("[")
    ? host.slice(1, host.indexOf("]")) // [::1]:port
    : host.split(":")[0];
  return (
    hostname === "127.0.0.1" || hostname === "localhost" || hostname === "::1"
  );
}

// Reject cross-origin browser requests. Non-browser clients (curl, the MCP
// server's fetch) send no Origin and pass; only a present, non-local Origin
// is rejected — this closes the CSRF / DNS-rebinding path from a web page.
function isAllowedOrigin(req: IncomingMessage): boolean {
  const origin = (req.headers.origin || "").toLowerCase();
  if (!origin) return true;
  return (
    origin === "http://127.0.0.1" ||
    origin === "http://localhost" ||
    origin.startsWith("http://127.0.0.1:") ||
    origin.startsWith("http://localhost:")
  );
}

// Require application/json. A cross-site "simple request" can only carry
// text/plain, urlencoded or multipart and skips the CORS preflight; refusing
// those content types closes that no-preflight CSRF bypass (OWASP).
function isJsonContentType(req: IncomingMessage): boolean {
  return (req.headers["content-type"] || "")
    .toLowerCase()
    .startsWith("application/json");
}

const httpServer = createServer(
  (req: IncomingMessage, res: ServerResponse) => {
    // CORS: restrict to localhost in local mode, allow configured origins in cloud
    const reqOrigin = req.headers.origin || "";
    const isLocalOrigin =
      reqOrigin === "http://127.0.0.1" ||
      reqOrigin === "http://localhost" ||
      reqOrigin.startsWith("http://127.0.0.1:") ||
      reqOrigin.startsWith("http://localhost:");
    const allowOrigin =
      HOST === "127.0.0.1"
        ? isLocalOrigin
          ? reqOrigin
          : "http://127.0.0.1"
        : reqOrigin || "*";
    res.setHeader("Access-Control-Allow-Origin", allowOrigin);
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    res.setHeader(
      "Access-Control-Allow-Headers",
      "Content-Type, Authorization",
    );

    if (req.method === "OPTIONS") {
      res.writeHead(204);
      res.end();
      return;
    }

    const parsedUrl = new URL(req.url || "/", `http://${HOST}:${PORT}`);

    if (req.method === "GET" && parsedUrl.pathname === "/status") {
      if (MULTI_USER) {
        const users = [...userSockets.entries()]
          .filter(([, ws]) => ws.readyState === WebSocket.OPEN)
          .map(([id]) => id);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ connected: users.length > 0, users }));
      } else {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(
          JSON.stringify({ connected: singleSocket !== null }),
        );
      }
      return;
    }

    if (req.method === "GET" && parsedUrl.pathname === "/debug") {
      const token =
        parsedUrl.searchParams.get("token") ||
        req.headers.authorization?.replace("Bearer ", "");
      if (!token || !isValidManualToken(token)) {
        res.writeHead(401, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "Unauthorized" }));
        return;
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(
        JSON.stringify(
          {
            mode: MULTI_USER ? "multi" : "single",
            log: debugLog,
            pending: pendingRequests.size,
            connected: MULTI_USER ? userSockets.size : singleSocket !== null,
            users: MULTI_USER ? [...userSockets.keys()] : undefined,
          },
          null,
          2,
        ),
      );
      return;
    }

    if (req.method === "POST" && parsedUrl.pathname === "/command") {
      if (!isAllowedHost(req)) {
        res.writeHead(403, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ success: false, data: { error: "Forbidden: invalid Host header" } }));
        return;
      }
      if (!isAllowedOrigin(req)) {
        res.writeHead(403, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ success: false, data: { error: "Forbidden: cross-origin request rejected" } }));
        return;
      }
      if (!isJsonContentType(req)) {
        res.writeHead(415, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ success: false, data: { error: "Content-Type must be application/json" } }));
        return;
      }
      if (!authenticateCommand(req)) {
        res.writeHead(401, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ success: false, data: { error: "Unauthorized" } }));
        return;
      }
      handleCommandRequest(req, res);
      return;
    }

    res.writeHead(404);
    res.end("Not found");
  },
);

async function handleCommandRequest(
  req: IncomingMessage,
  res: ServerResponse,
) {
  const MAX_BODY = 10 * 1024 * 1024; // 10 MB
  let body = "";
  for await (const chunk of req) {
    body += typeof chunk === "string"
      ? chunk
      : (chunk as Buffer).toString("utf-8");
    if (body.length > MAX_BODY) {
      res.writeHead(413, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ success: false, data: { error: "Request body too large" } }));
      return;
    }
  }

  let command: {
    id?: string;
    action?: string;
    params?: unknown;
    userId?: string;
  };
  try {
    command = JSON.parse(body);
  } catch {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({ success: false, data: { error: "Invalid JSON" } }),
    );
    return;
  }

  if (!command.action || typeof command.action !== "string") {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ success: false, data: { error: "Missing or invalid action" } }));
    return;
  }

  const ws = getSocket(command.userId);
  if (!ws) {
    const target = MULTI_USER
      ? `user "${command.userId || "default"}"`
      : "extension";
    addLog("← tool", `503: ${target} not connected`);
    res.writeHead(503, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({
        success: false,
        data: { error: `Browser extension not connected${MULTI_USER ? ` for user "${command.userId || "default"}"` : ""}` },
      }),
    );
    return;
  }

  const id =
    command.id ||
    `cmd-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const fullCommand = {
    v: "1.1",
    id,
    action: command.action,
    params: command.params || {},
  };

  addLog("→ tool", `received: ${command.action}`, command.params);
  addLog("→ ext", `forward: ${command.action} (${id})`);
  try {
    ws.send(JSON.stringify(fullCommand));
  } catch {
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      success: false,
      data: { error: "Failed to send command to extension" },
    }));
    return;
  }

  const result = await new Promise<unknown>((resolve) => {
    const timer = setTimeout(() => {
      pendingRequests.delete(id);
      addLog("← ext", `TIMEOUT: ${command.action} (${id})`);
      resolve({
        v: "1.1",
        id,
        success: false,
        data: { error: "Timeout: extension did not respond within 30s" },
      });
    }, COMMAND_TIMEOUT_MS);

    const requestUserId = command.userId || "default";
    pendingRequests.set(id, { resolve, timer, userId: requestUserId });
  });

  const r = result as {
    success?: boolean;
    data?: { error?: string; pageUrl?: string };
  };
  addLog(
    "← tool",
    `response: ${command.action} success=${r.success}`,
    r.data?.error || r.data?.pageUrl || "",
  );

  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify(result));
}

// ── WebSocket server ─────────────────────────────────────────────

const wss = new WebSocketServer({ noServer: true });

httpServer.on("upgrade", (req, socket, head) => {
  const auth = authenticateUpgrade(req);
  if (!auth.ok) {
    socket.write("HTTP/1.1 401 Unauthorized\r\n\r\n");
    socket.destroy();
    const origin = req.headers.origin || "(none)";
    addLog("system", `rejected: origin=${origin}`);
    return;
  }

  wss.handleUpgrade(req, socket, head, (ws) => {
    wss.emit("connection", ws, req, auth.userId);
  });
});

wss.on(
  "connection",
  (ws: WebSocket, req: IncomingMessage, userId: string) => {
    setSocket(userId, ws);
    const origin = req.headers.origin || "unknown";
    addLog(
      "system",
      `extension connected (userId: ${userId}, origin: ${origin})`,
    );

    ws.on("message", (raw) => {
      let msg: {
        type?: string;
        id?: string;
        success?: boolean;
        data?: { error?: string; pageUrl?: string };
      };
      try {
        msg = JSON.parse(raw.toString());
      } catch {
        return;
      }

      if (msg.type === "ping") {
        ws.send(JSON.stringify({ type: "pong" }));
        return;
      }

      addLog(
        "← ext",
        `result: id=${msg.id} success=${msg.success}`,
        msg.data?.error || msg.data?.pageUrl || "",
      );

      if (msg.id && pendingRequests.has(msg.id)) {
        const pending = pendingRequests.get(msg.id)!;
        clearTimeout(pending.timer);
        pendingRequests.delete(msg.id);
        pending.resolve(msg);
      }
    });

    ws.on("close", () => {
      addLog("system", `extension disconnected (userId: ${userId})`);
      removeSocket(userId, ws);

      // Clean up pending requests belonging to this user only
      for (const [id, pending] of pendingRequests) {
        if (pending.userId !== userId) continue;
        clearTimeout(pending.timer);
        pendingRequests.delete(id);
        pending.resolve({
          v: "1.1",
          id,
          success: false,
          data: { error: "Extension disconnected" },
        });
      }
    });

    ws.on("error", (err) => {
      console.error(
        `[browserhand] WebSocket error (userId: ${userId}):`,
        err.message,
      );
    });
  },
);

// ── Start ────────────────────────────────────────────────────────

httpServer.on("error", (err: NodeJS.ErrnoException) => {
  if (err.code === "EADDRINUSE") {
    console.error(`\n  Port ${PORT} is already in use. Is another relay running?\n`);
  } else {
    console.error(`\n  HTTP server error: ${err.message}\n`);
  }
  process.exit(1);
});

httpServer.listen(PORT, HOST, () => {
  const mode = MULTI_USER ? "multi-user" : "single-user";
  const auth = API_KEY
    ? "API key required"
    : REQUIRE_LOCAL_AUTH
      ? "local token required"
      : "no auth (local mode)";
  const authHeader = API_KEY
    ? ` -H "Authorization: Bearer $BROWSERHAND_API_KEY"`
    : REQUIRE_LOCAL_AUTH
      ? ` -H "Authorization: Bearer ${MANUAL_TOKEN}"`
      : "";
  console.log(`\n  🔌 BrowserHand Relay`);
  console.log(`  ├─ Listening on ${HOST}:${PORT}`);
  console.log(`  ├─ Mode: ${mode}`);
  console.log(`  ├─ Command auth: ${auth}`);
  console.log(`  ├─ Manual Token: ${MANUAL_TOKEN}`);
  console.log(`  ├─ POST /command | GET /status`);
  console.log(
    `  └─ Test: curl -X POST http://${HOST}:${PORT}/command` +
      ` -H "Content-Type: application/json"${authHeader}` +
      ` -d '{"action":"navigate","params":{"url":"https://example.com"}}'\n`,
  );
});
