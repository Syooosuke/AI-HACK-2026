"use client";

/** 画面① 依頼作成（docs/05-frontend.md 画面①）。 */

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useMemo, useState } from "react";

import { LocationPicker, type PickedLocation } from "@/components/map/LocationPicker";
import { PresetChips } from "@/components/task/PresetChips";
import { Button, Card, SectionTitle } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { createTask, generateTaskDescription } from "@/lib/api/tasks";
import { isoToLocalInput, localInputToIso, minutesFromNow } from "@/lib/datetime";
import { env } from "@/lib/env";
import { saveReview } from "@/lib/reviewHandoff";
import type { TaskPreset } from "@/lib/taskPresets";

const MAX_REFERENCE_IMAGES = 3;
const DESCRIPTION_MIN = 10;
const DESCRIPTION_MAX = 1000;
const TITLE_MAX = 60;

/** サーバー側の SCHEDULE_PAST_TOLERANCE と揃える。 */
const PAST_TOLERANCE_MS = 15 * 60 * 1000;

/**
 * `datetime-local` はブラウザ既定の最小幅を持つため、`w-full` だけだと
 * 親からはみ出す（iOS Safari で顕著）。`min-w-0` で縮めるようにし、
 * `appearance-none` で端末ごとの余計な装飾を外す。
 */
const DATETIME_INPUT_CLASS =
  "block w-full min-w-0 max-w-full appearance-none rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-slate-800";

export default function NewTaskPage() {
  const router = useRouter();
  const toast = useToast();

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [location, setLocation] = useState<PickedLocation>({
    lat: env.defaultMapCenter.lat,
    lng: env.defaultMapCenter.lng,
    address: null,
  });
  // 既定は「今から」。すぐ撮ってほしい依頼が最も多く、毎回入力し直す手間を省く
  const [scheduledAt, setScheduledAt] = useState(() => isoToLocalInput(new Date()));
  const [deadlineAt, setDeadlineAt] = useState(() => isoToLocalInput(minutesFromNow(60 * 6)));
  const [workerCount, setWorkerCount] = useState(1);
  const [minRating, setMinRating] = useState<number | null>(null);
  const [reward, setReward] = useState(2000);
  const [images, setImages] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [generatingDescription, setGeneratingDescription] = useState(false);

  const errors = useMemo(() => {
    const found: Record<string, string> = {};
    if (!title.trim()) found.title = "タイトルを入力してください。";
    if (title.length > TITLE_MAX) found.title = `${TITLE_MAX}文字以内で入力してください。`;
    if (description.trim().length < DESCRIPTION_MIN) {
      found.description = `詳細メッセージは${DESCRIPTION_MIN}文字以上で入力してください。`;
    }
    if (description.length > DESCRIPTION_MAX) {
      found.description = `${DESCRIPTION_MAX}文字以内で入力してください。`;
    }
    if (!scheduledAt) found.scheduledAt = "撮影希望日時を指定してください。";
    if (!deadlineAt) found.deadlineAt = "提出期限を指定してください。";
    // 「今」を選べるようにする。入力欄は分単位のため、選んだ時点ですでに数十秒過去に
    // なっている。サーバー側も同じ幅（15分）を許容している
    if (scheduledAt && new Date(scheduledAt).getTime() < Date.now() - PAST_TOLERANCE_MS) {
      found.scheduledAt = "過去の日時は指定できません。";
    }
    if (scheduledAt && deadlineAt && new Date(deadlineAt) < new Date(scheduledAt)) {
      found.deadlineAt = "撮影希望日時以降を指定してください。";
    }
    if (reward < 100 || reward > 100000) found.reward = "報酬は100〜100,000円で指定してください。";
    return found;
  }, [title, description, scheduledAt, deadlineAt, reward]);

  const canSubmit = Object.keys(errors).length === 0 && !submitting;

  /**
   * タイトル側のチップ。詳細が空のときは詳細もまとめて埋める（入力の手間を減らす）。
   * 選択済みのチップを再タップしたら消す。まとめて入れた詳細も、手で書き換えていなければ一緒に消す。
   */
  const applyPresetToTitle = (preset: TaskPreset, active: boolean) => {
    if (active) {
      setTitle("");
      if (description.trim() === preset.description.trim()) setDescription("");
      return;
    }
    setTitle(preset.title);
    if (!description.trim()) setDescription(preset.description);
  };

  /** 詳細側のチップ。再タップで詳細を空にする。 */
  const applyPresetToDescription = (preset: TaskPreset, active: boolean) => {
    setDescription(active ? "" : preset.description);
  };

  const onPickImages = (files: FileList | null) => {
    if (!files) return;
    const merged = [...images, ...Array.from(files)].slice(0, MAX_REFERENCE_IMAGES);
    setImages(merged);
  };

  const generateDescription = async () => {
    const normalizedTitle = title.trim();
    if (!normalizedTitle) {
      toast.error("先に依頼タイトルを入力してください。");
      return;
    }
    if (
      description.trim() &&
      !window.confirm("入力済みの詳細メッセージをAI生成した文章に置き換えますか？")
    ) {
      return;
    }

    setGeneratingDescription(true);
    try {
      const generated = await generateTaskDescription(normalizedTitle);
      setDescription(generated.description);
      toast.success("詳細メッセージを生成しました。内容を確認して必要に応じて編集してください。");
    } catch (cause) {
      toast.error(toMessage(cause));
    } finally {
      setGeneratingDescription(false);
    }
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      const review = await createTask({
        title: title.trim(),
        description: description.trim(),
        locationLat: location.lat,
        locationLng: location.lng,
        locationAddress: location.address,
        scheduledAt: localInputToIso(scheduledAt),
        deadlineAt: localInputToIso(deadlineAt),
        rewardAmount: reward,
        requiredWorkerCount: workerCount,
        minWorkerRating: minRating,
        referenceImages: images,
      });
      saveReview(review);
      router.push("/requests/new/review");
    } catch (cause) {
      toast.error(toMessage(cause));
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-5 md:mx-auto md:max-w-2xl">
      <h1 className="text-lg font-bold text-slate-800">依頼を作成</h1>

      <div className="-mt-3">
        <Link
          href="/requests"
          className="inline-flex items-center rounded-lg border border-client px-3 py-2 text-xs font-bold text-client transition hover:bg-blue-50"
        >
          過去の依頼を複製
        </Link>
      </div>

      <Card className="space-y-3">
        <SectionTitle>1. 撮影地点を指定</SectionTitle>
        <LocationPicker value={location} onChange={setLocation} />
      </Card>

      <Card className="space-y-3">
        <SectionTitle>2. 日時を指定</SectionTitle>
        <Field label="撮影希望日時" error={errors.scheduledAt}>
          <input
            type="datetime-local"
            value={scheduledAt}
            onChange={(e) => setScheduledAt(e.target.value)}
            className={DATETIME_INPUT_CLASS}
          />
        </Field>
        <Field label="提出期限" error={errors.deadlineAt}>
          <input
            type="datetime-local"
            value={deadlineAt}
            onChange={(e) => setDeadlineAt(e.target.value)}
            className={DATETIME_INPUT_CLASS}
          />
        </Field>
      </Card>

      <Card className="space-y-4">
        <div>
          <SectionTitle>3. 撮影人数</SectionTitle>
          <div className="flex items-center gap-4">
            <Stepper value={workerCount} min={1} max={10} onChange={setWorkerCount} />
            <p className="text-xs text-slate-500">同じ地点を最大10人まで依頼できます</p>
          </div>

          <div className="mt-4 border-t border-slate-100 pt-3">
            <p className="mb-1 text-xs font-bold text-slate-500">受注できるワーカーを絞る（任意）</p>
            <p className="mb-2 text-xs text-slate-500">
              過去に受け取った星評価の平均で絞り込めます。
              <span className="font-bold">評価がまだ無いワーカーは対象に含まれます</span>
              （評価を得る機会がなくなってしまうため）。
            </p>
            <RatingFilter value={minRating} onChange={setMinRating} />
          </div>
        </div>
        <Field label="4. 報酬（1人あたり・円）" error={errors.reward}>
          <input
            type="number"
            min={100}
            max={100000}
            step={100}
            value={reward}
            onChange={(e) => setReward(Number(e.target.value))}
            className="w-full rounded-xl border border-slate-300 px-3 py-2.5"
          />
        </Field>
      </Card>

      <Card className="space-y-4">
        <div className="space-y-2">
          <SectionTitle>5. 依頼タイトル</SectionTitle>
          <p className="text-xs text-slate-500">
            よくある依頼はタップで入力できます（詳細が空のときは詳細も一緒に入ります）。
            選択中のチップをもう一度タップすると消えます
          </p>
          <PresetChips onPick={applyPresetToTitle} currentValue={title} field="title" />
          <Field label="" error={errors.title}>
            <input
              type="text"
              value={title}
              maxLength={TITLE_MAX}
              placeholder="駅前の再開発工事の進捗確認"
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3 py-2.5"
            />
          </Field>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <SectionTitle>6. 詳細メッセージ</SectionTitle>
            <button
              type="button"
              onClick={() => void generateDescription()}
              disabled={!title.trim() || generatingDescription || submitting}
              className="shrink-0 rounded-lg border border-violet-300 bg-violet-50 px-3 py-1.5 text-xs font-bold text-violet-700 transition hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {generatingDescription ? "AIが作成中…" : "AIで詳細を作成"}
            </button>
          </div>
          <p className="text-xs text-slate-500">
            タイトルから短い依頼文を生成できます。生成後も自由に編集できます
          </p>
          <PresetChips
            onPick={applyPresetToDescription}
            currentValue={description}
            field="description"
          />
          <Field label="" error={errors.description}>
            <textarea
              value={description}
              rows={5}
              maxLength={DESCRIPTION_MAX}
              placeholder="周辺の工事状況や交通状況を確認してください。"
              onChange={(e) => setDescription(e.target.value)}
              disabled={generatingDescription}
              className="w-full rounded-xl border border-slate-300 px-3 py-2.5"
            />
          </Field>
          <p className="text-right text-xs text-slate-400">
            {description.length} / {DESCRIPTION_MAX}
          </p>
        </div>
      </Card>

      <Card className="space-y-3">
        <SectionTitle>7. 参考画像（任意・最大3枚）</SectionTitle>
        <div className="flex flex-wrap gap-2">
          {images.map((file, index) => (
            <div
              key={`${file.name}-${index}`}
              className="relative h-20 w-20 overflow-hidden rounded-xl border border-slate-200"
            >
              {/* next/image はローカルの File を扱えないため object URL を使う */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={URL.createObjectURL(file)}
                alt={`参考画像${index + 1}`}
                className="h-full w-full object-cover"
              />
              <button
                type="button"
                onClick={() => setImages(images.filter((_, i) => i !== index))}
                className="absolute right-0 top-0 bg-black/60 px-1.5 text-xs text-white"
                aria-label="削除"
              >
                ×
              </button>
            </div>
          ))}
          {images.length < MAX_REFERENCE_IMAGES && (
            <label className="flex h-20 w-20 cursor-pointer items-center justify-center rounded-xl border-2 border-dashed border-slate-300 text-2xl text-slate-400">
              ＋
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
                className="hidden"
                onChange={(e) => onPickImages(e.target.files)}
              />
            </label>
          )}
        </div>
      </Card>

      <div className="space-y-2">
        <Button accent="client" onClick={() => void submit()} disabled={!canSubmit} loading={submitting}>
          {submitting ? "AIが依頼内容を審査しています…" : "依頼内容を確認"}
        </Button>
        {submitting && (
          <p className="text-center text-xs text-slate-500">
            審査には30秒〜1分ほどかかります。画面を閉じずにお待ちください。
          </p>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      {label && <span className="mb-1 block text-xs font-bold text-slate-500">{label}</span>}
      {children}
      {error && <span className="mt-1 block text-xs text-fail">{error}</span>}
    </label>
  );
}

/** 受注できるワーカーの最低平均評価。「指定なし」を含めた選択肢から選ぶ。 */
function RatingFilter({
  value,
  onChange,
}: {
  value: number | null;
  onChange: (next: number | null) => void;
}) {
  const options: { label: string; value: number | null }[] = [
    { label: "指定なし", value: null },
    { label: "★3.0以上", value: 3.0 },
    { label: "★3.5以上", value: 3.5 },
    { label: "★4.0以上", value: 4.0 },
    { label: "★4.5以上", value: 4.5 },
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const active = value === option.value;
        return (
          <button
            key={option.label}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={`rounded-full border px-3 py-1.5 text-xs font-bold transition ${
              active
                ? "border-client bg-client text-white"
                : "border-slate-300 text-slate-600 hover:bg-slate-50"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function Stepper({
  value,
  min,
  max,
  onChange,
}: {
  value: number;
  min: number;
  max: number;
  onChange: (next: number) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={() => onChange(Math.max(min, value - 1))}
        className="h-9 w-9 rounded-full border border-slate-300 text-lg font-bold text-slate-600 disabled:opacity-30"
        disabled={value <= min}
        aria-label="減らす"
      >
        −
      </button>
      <span className="w-10 text-center text-lg font-bold tabular-nums">{value}</span>
      <button
        type="button"
        onClick={() => onChange(Math.min(max, value + 1))}
        className="h-9 w-9 rounded-full border border-slate-300 text-lg font-bold text-slate-600 disabled:opacity-30"
        disabled={value >= max}
        aria-label="増やす"
      >
        ＋
      </button>
    </div>
  );
}
