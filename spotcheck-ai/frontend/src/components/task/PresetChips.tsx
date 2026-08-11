"use client";

/**
 * よくある依頼のクイック入力。タップすると対象のテキスト欄へ文章が入る。
 * 依頼タイトル・詳細メッセージのそれぞれの隣に置く。
 */

import { TASK_PRESETS, type TaskPreset } from "@/lib/taskPresets";

export function PresetChips({
  onPick,
  /** いまテキスト欄に入っている値。一致するチップを選択済みとして示す。 */
  currentValue,
  /** チップが入れる値（タイトル or 詳細）。選択状態の判定に使う。 */
  field,
}: {
  onPick: (preset: TaskPreset) => void;
  currentValue: string;
  field: "title" | "description";
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {TASK_PRESETS.map((preset) => {
        const active = currentValue.trim() === preset[field].trim();
        return (
          <button
            key={preset.id}
            type="button"
            onClick={() => onPick(preset)}
            aria-pressed={active}
            className={`flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-bold transition ${
              active
                ? "border-client bg-blue-50 text-client"
                : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            }`}
          >
            <span aria-hidden>{preset.icon}</span>
            {preset.label}
          </button>
        );
      })}
    </div>
  );
}
