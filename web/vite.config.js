import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "url";
import path from "path";
import fs from "fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = path.resolve(__dirname, "../data");

// 開發時把 /data/*.json 直接從 repo 的 ../data 餵出去(不複製 78MB 進 web/)
function serveData() {
  return {
    name: "serve-repo-data",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const m = req.url && req.url.match(/\/data\/(.+?\.json)(?:\?.*)?$/);
        if (m) {
          const fp = path.join(DATA_DIR, decodeURIComponent(m[1]));
          if (fp.startsWith(DATA_DIR) && fs.existsSync(fp)) {
            res.setHeader("Content-Type", "application/json; charset=utf-8");
            res.setHeader("Cache-Control", "no-cache");
            fs.createReadStream(fp).pipe(res);
            return;
          }
          res.statusCode = 404;
          res.end("not found");
          return;
        }
        next();
      });
    },
  };
}

export default defineConfig({
  base: "/tw-financial-report/", // GitHub Project Pages 子路徑
  plugins: [react(), serveData()],
});
