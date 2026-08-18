import { defineConfig, type ViteDevServer, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from "vite-tsconfig-paths";
import { generateLessonAnalysis } from "./api/generate-lesson";
import { documentIntelligenceProxyPlugin } from "./api/di-proxy";

// 自定义 API 中间件：提供 /api/generate-lesson-analysis 端点
function lessonAnalysisApiPlugin() {
  return {
    name: 'lesson-analysis-api',
    configureServer(server: ViteDevServer) {
      server.middlewares.use('/api/generate-lesson-analysis', async (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405;
          res.end(JSON.stringify({ error: 'Method not allowed' }));
          return;
        }

        // 读取 POST body
        let body = '';
        for await (const chunk of req) {
          body += chunk;
        }

        let reqData: { lessonId?: string };
        try {
          reqData = JSON.parse(body);
        } catch {
          res.statusCode = 400;
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify({ error: 'Invalid JSON body' }));
          return;
        }

        const { lessonId } = reqData;
        if (!lessonId) {
          res.statusCode = 400;
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify({ error: 'Missing lessonId' }));
          return;
        }

        const projectRoot = process.cwd();

        try {
          const result = await generateLessonAnalysis(
            lessonId,
            (id) => server.ssrLoadModule(id),
            projectRoot,
          );

          res.statusCode = result.success ? 200 : 207;
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify(result));
        } catch (err) {
          const errMsg = err instanceof Error ? err.message : String(err);
          res.statusCode = 500;
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify({
            success: false,
            lessonId,
            error: `服务器内部错误: ${errMsg}`,
          }));
        }
      });
    },
  };
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 加载 .env 文件中的环境变量到 process.env
  loadEnv(mode, process.cwd(), '');

  return {
    build: {
      sourcemap: 'hidden',
    },
    plugins: [
      react({
        babel: {
          plugins: [
            'react-dev-locator',
          ],
        },
      }),
      tsconfigPaths(),
      lessonAnalysisApiPlugin(),
      documentIntelligenceProxyPlugin(),
    ],
  };
})
