import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

// 篩選/排序狀態同步到網址 query，讓上一頁、重整、分享連結都能還原。
// defaults 必須是 module-level 常數(identity 要穩)；值型別只支援 string / boolean。
// 等於預設值就不寫進網址(網址保持乾淨)，其餘一律寫入 — 空字串也算「使用者刻意清空」。
export function useUrlState(defaults) {
  const [params, setParams] = useSearchParams();

  const state = useMemo(() => {
    const s = { ...defaults };
    for (const k of Object.keys(defaults)) {
      const v = params.get(k);
      if (v == null) continue;
      s[k] = typeof defaults[k] === "boolean" ? v === "1" : v;
    }
    return s;
  }, [params, defaults]);

  // 一次收整個 patch：setParams 的 prev 取自當前 render 的 location，
  // 同一 tick 連呼兩次後者會蓋掉前者(排序要同時改 key+dir，踩過)。
  // replace: 篩選是同一畫面的微調，不該塞爆 history(否則要按 N 次上一頁才離開)
  const set = useCallback(
    (patch) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const [k, v] of Object.entries(patch)) {
            if (v === defaults[k]) next.delete(k);
            else next.set(k, v === true ? "1" : v === false ? "0" : v);
          }
          return next;
        },
        { replace: true }
      ),
    [setParams, defaults]
  );

  return [state, set];
}
