/** 再撮影指示の表示（画面⑧）。`issues` を赤いエラー行として列挙する。 */

import type { Issue } from "@/types/api";

export function IssueList({ issues }: { issues: Issue[] }) {
  if (issues.length === 0) return null;
  return (
    <ul className="space-y-2">
      {issues.map((issue, index) => (
        <li
          key={`${issue.code}-${index}`}
          className="flex items-start gap-2 rounded-xl bg-red-50 px-3 py-2.5 text-sm text-red-700"
        >
          <span aria-hidden className="mt-0.5 font-bold">
            !
          </span>
          <span>
            {issue.message}
            <span className="ml-1 font-mono text-[10px] text-red-400">{issue.code}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
