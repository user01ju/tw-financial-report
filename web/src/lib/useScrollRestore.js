import { useEffect } from "react";

// 列表頁捲動位置記在 sessionStorage，點進個股再返回時回到原處。
// ready 表示表格已渲染(rows 載入完)，否則頁面還沒撐高，scrollTo 會被吃掉。
export function useScrollRestore(key, ready) {
  useEffect(() => {
    const onScroll = () => sessionStorage.setItem(`scroll:${key}`, String(window.scrollY));
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [key]);

  useEffect(() => {
    if (!ready) return;
    const y = +(sessionStorage.getItem(`scroll:${key}`) || 0);
    if (y) window.scrollTo(0, y); // effect 跑時 DOM 已 commit，頁面高度到位
  }, [ready, key]);
}
