"use client";

/**
 * 地名・住所での場所検索。
 *
 * - Places API が使えるときは入力に応じた候補（オートコンプリート）を出す
 * - Places API が無効なキーでは Geocoder のテキスト検索へフォールバックし、
 *   入力を確定（Enter / 検索ボタン）したときにまとめて検索する
 *
 * 選択された地点は `onSelect` で親（地図）へ渡す。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Spinner } from "@/components/ui";
import type { GAutocompletePrediction, GPlacesService } from "@/types/google-maps";

export type SearchedPlace = {
  lat: number;
  lng: number;
  address: string | null;
};

/** 入力から候補取得までの待ち時間（ミリ秒）。打つたびに問い合わせないための間引き。 */
const DEBOUNCE_MS = 350;
const MIN_QUERY_LENGTH = 2;

export function PlaceSearchBox({
  onSelect,
  placeholder = "地名・住所で検索（例: 渋谷駅）",
  accent = "client",
}: {
  onSelect: (place: SearchedPlace) => void;
  placeholder?: string;
  accent?: "client" | "worker";
}) {
  const [query, setQuery] = useState("");
  const [predictions, setPredictions] = useState<GAutocompletePrediction[]>([]);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const placesServiceRef = useRef<GPlacesService | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const accentClass = accent === "worker" ? "bg-worker" : "bg-client";

  const places = useMemo(() => window.google?.maps.places, []);

  const clearSuggestions = useCallback(() => {
    setPredictions([]);
  }, []);

  /** Geocoder によるテキスト検索（Places が無い場合、または候補が取れない場合）。 */
  const searchByGeocoder = useCallback(
    (text: string) => {
      const maps = window.google?.maps;
      if (!maps) return;
      setPending(true);
      setMessage(null);
      new maps.Geocoder().geocode(
        { address: text, language: "ja", region: "JP" },
        (results, status) => {
          setPending(false);
          const location = results?.[0]?.geometry?.location;
          if (status !== "OK" || !location) {
            setMessage("見つかりませんでした。別の地名や住所で試してください。");
            return;
          }
          clearSuggestions();
          onSelect({
            lat: location.lat(),
            lng: location.lng(),
            address: results?.[0]?.formatted_address ?? text,
          });
        },
      );
    },
    [clearSuggestions, onSelect],
  );

  // 入力に応じて候補を取得する（Places が使える場合のみ）
  useEffect(() => {
    if (!places) return;
    const text = query.trim();
    if (text.length < MIN_QUERY_LENGTH) {
      clearSuggestions();
      return;
    }
    const timer = window.setTimeout(() => {
      const service = new places.AutocompleteService();
      service.getPlacePredictions(
        { input: text, language: "ja", componentRestrictions: { country: "jp" } },
        (results, status) => {
          if (status !== places.PlacesServiceStatus.OK || !results) {
            clearSuggestions();
            return;
          }
          setPredictions(results.slice(0, 5));
        },
      );
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query, places, clearSuggestions]);

  // 候補の外側をタップしたら閉じる
  useEffect(() => {
    if (predictions.length === 0) return;
    const handle = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) clearSuggestions();
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [predictions.length, clearSuggestions]);

  const choosePrediction = (prediction: GAutocompletePrediction) => {
    if (!places) return;
    setQuery(prediction.structured_formatting?.main_text ?? prediction.description);
    clearSuggestions();
    setPending(true);
    setMessage(null);

    // 候補には座標が含まれないため、詳細取得で座標を得る
    placesServiceRef.current ??= new places.PlacesService(document.createElement("div"));
    placesServiceRef.current.getDetails(
      {
        placeId: prediction.place_id,
        fields: ["geometry", "formatted_address", "name"],
        language: "ja",
      },
      (place, status) => {
        setPending(false);
        const location = place?.geometry?.location;
        if (status !== places.PlacesServiceStatus.OK || !location) {
          // 詳細が取れない場合はテキスト検索で救済する
          searchByGeocoder(prediction.description);
          return;
        }
        onSelect({
          lat: location.lat(),
          lng: location.lng(),
          address: place?.formatted_address ?? place?.name ?? prediction.description,
        });
      },
    );
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const text = query.trim();
    if (text.length === 0) return;
    // 候補が出ていれば先頭を採用し、無ければテキスト検索する
    if (predictions.length > 0) {
      choosePrediction(predictions[0]);
      return;
    }
    searchByGeocoder(text);
  };

  return (
    <div ref={containerRef} className="relative">
      <form onSubmit={submit} className="flex gap-2">
        <input
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setMessage(null);
          }}
          placeholder={placeholder}
          aria-label="場所を検索"
          className="min-w-0 flex-1 rounded-xl border border-slate-300 px-3 py-2.5 text-sm"
        />
        <button
          type="submit"
          disabled={query.trim().length === 0 || pending}
          className={`flex w-20 items-center justify-center rounded-xl px-3 py-2.5 text-xs font-bold text-white disabled:opacity-40 ${accentClass}`}
        >
          {pending ? <Spinner className="h-4 w-4 border-white/40 border-t-white" /> : "検索"}
        </button>
      </form>

      {predictions.length > 0 && (
        <ul className="absolute inset-x-0 top-full z-20 mt-1 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg">
          {predictions.map((prediction) => (
            <li key={prediction.place_id}>
              <button
                type="button"
                onClick={() => choosePrediction(prediction)}
                className="block w-full px-3 py-2.5 text-left hover:bg-slate-50"
              >
                <span className="block text-sm text-slate-800">
                  {prediction.structured_formatting?.main_text ?? prediction.description}
                </span>
                {prediction.structured_formatting?.secondary_text && (
                  <span className="block text-xs text-slate-500">
                    {prediction.structured_formatting.secondary_text}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      {message && <p className="mt-1 text-xs text-amber-700">{message}</p>}
    </div>
  );
}
