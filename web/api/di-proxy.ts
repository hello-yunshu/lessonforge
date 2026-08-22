/**
 * document-intelligence 纯透传代理（界面与引擎分离）。
 *
 * 仅做 HTTP 转发：/api/di/v1/textbook/... → <DI_SERVICE_URL>/v1/textbook/...，
 * 以及 /api/di/health 健康检查。
 *
 * 所有「按章节解析 → 结构恢复 → 教育对象识别 → 人工标注 → 自学习回灌」的
 * 编排逻辑均已下沉到 document-intelligence 引擎内的 textbook 模块
 * （document-intelligence/src/document_intelligence/api/textbook.py），
 * 前端只负责透传，两者可独立更新、互不牵连。
 *
 * 服务地址通过环境变量 DI_SERVICE_URL 配置，默认 http://localhost:8080。
 */
import type { ViteDevServer } from "vite";
import type { IncomingMessage, ServerResponse } from "node:http";
import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";

const DI_SERVICE_URL = (process.env.DI_SERVICE_URL || "http://localhost:8080").replace(/\/+$/, "");

function send(res: ServerResponse, status: number, data: unknown): void {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(data));
}

async function readJson(res: Response): Promise<{ status: number; body: unknown }> {
  const text = await res.text();
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    body = text;
  }
  return { status: res.status, body };
}

// 通用转发：/api/di/<path> → <DI_SERVICE_URL>/<path>
// 使用 node:http request 而非全局 fetch：undici 默认 headersTimeout/bodyTimeout 为
// 300s，而教材解析可能耗时超过 5 分钟，会导致代理提前超时返回 502。node:http 默认
// 无该超时限制，可完整等待引擎解析完成。
function forward(
  req: IncomingMessage,
  res: ServerResponse,
  targetPath: string,
): void {
  const parsed = new URL(`${DI_SERVICE_URL}/${targetPath}`);
  const isHttps = parsed.protocol === "https:";

  // 读取请求体（含 multipart）
  const chunks: Buffer[] = [];
  req.on("data", (chunk: Buffer) => chunks.push(chunk));
  req.on("end", () => {
    const body = Buffer.concat(chunks);

    const headers: Record<string, string> = {};
    for (const [k, v] of Object.entries(req.headers)) {
      if (v === undefined) continue;
      headers[k] = Array.isArray(v) ? v.join(", ") : v;
    }
    // hop-by-hop 头不转发
    ["host", "content-length", "connection"].forEach((h) => delete headers[h]);
    if (body.length > 0) {
      headers["content-length"] = String(body.length);
    }

    const makeRequest = isHttps ? httpsRequest : httpRequest;
    let responded = false;
    const upstreamReq = makeRequest(
      {
        hostname: parsed.hostname,
        port: parsed.port || (isHttps ? 443 : 80),
        path: parsed.pathname + parsed.search,
        method: req.method ?? "GET",
        headers,
      },
      (upstreamRes) => {
        responded = true;
        res.statusCode = upstreamRes.statusCode ?? 502;
        for (const [k, v] of Object.entries(upstreamRes.headers)) {
          if (v === undefined) continue;
          const lk = k.toLowerCase();
          if (lk === "content-length" || lk === "transfer-encoding") continue;
          res.setHeader(k, v);
        }
        upstreamRes.pipe(res);
      },
    );

    upstreamReq.on("error", (err) => {
      const msg = err instanceof Error ? err.message : String(err);
      if (responded || res.headersSent) {
        res.destroy();
        return;
      }
      send(res, 502, {
        error: `无法连接 document-intelligence 服务 (${DI_SERVICE_URL}): ${msg}`,
        hint: "请先运行 启动文档智能解析服务.bat 启动 FastAPI 服务。",
      });
    });

    if (body.length > 0) upstreamReq.write(body);
    upstreamReq.end();
  });
}

// Vite 中间件插件
export function documentIntelligenceProxyPlugin() {
  return {
    name: "document-intelligence-proxy",
    configureServer(server: ViteDevServer) {
      server.middlewares.use("/api/di", async (req, res) => {
        const url = req.url ?? "/";
        const targetPath = url.replace(/^\/+/, "");

        // 健康检查
        if (targetPath === "health" || targetPath === "healthz") {
          try {
            const resp = await fetch(`${DI_SERVICE_URL}/healthz`);
            const { status, body } = await readJson(resp);
            send(res, status, {
              service: "document-intelligence",
              upstream: DI_SERVICE_URL,
              ...(typeof body === "object" ? body : { body }),
            });
          } catch {
            send(res, 503, {
              service: "document-intelligence",
              upstream: DI_SERVICE_URL,
              error: "document-intelligence 服务未启动",
              hint: "请先运行 启动文档智能解析服务.bat",
            });
          }
          return;
        }

        // 其余路径透传（含 /v1/textbook/... 编排端点）
        await forward(req, res, targetPath);
      });
    },
  };
}
