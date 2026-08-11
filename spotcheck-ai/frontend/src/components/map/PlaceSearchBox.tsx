"use client";

/**
 * 地名・住所での場所検索。
 *
 * Google の有効なAPIに応じて、使える手段を順に試す。
 * 1. Places API (New) の候補取得（`AutocompleteSuggestion`）
 * 2. 旧 Places の候補取得（`AutocompleteService`）
 * 3. Geocoder のテキスト検索（確定時のみ。候補は出ない）
 *
 * **どれも使えない場合は理由をそのまま画面に出す。**
 * Geocoding / Places は課金の有効化とAPIの有効化が必要で、未設定だと Google が
 * `REQUEST_DENIED` を返す。原因が分からないと「検索が壊れている」ように見えるため、
 * 状態コードごとに対処方法を日本語で表示する。
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { Spinner } from "@/components/ui";
import type { GPlaceNew } from "@/types/google-maps";

export type SearchedPlace = {
  lat: number;
  lng: number;
  address: string | null;
};

/** 画面に出す候補（新旧APIの差を吸収した形）。 */
type Suggestion = {
  id: string;
  mainText: string;
  secondaryText?: string;
  /** 新APIのときのみ。座標取得に使う。 */
  place?: GPlaceNew;
  /** 旧APIのときのみ。 */
  legacyPlaceId?: string;
  /** Geocoder へのフォールバック用。 */
  fallbackQuery: string;
};

/** 入力から候補取得までの待ち時間（ミリ秒）。打つたびに問い合わせないための間引き。 */
const DEBOUNCE_MS = 350;
const MIN_QUERY_LENGTH = 2;
const MAX_SUGGESTIONS = 5;

/** Google の状態コードごとの対処方法。原因を隠さず具体的に出す。 */
const STATUS_MESSAGE: Record<string, string> = {
  ZERO_RESULTS: "見つかりませんでした。別の地名や住所で試してください。",
  REQUEST_DENIED:
    "Google側で検索APIが許可されていません（Google Cloud で課金の有効化と Geocoding API / Places API (New) の有効化が必要です）。",
  OVER_QUERY_LIMIT: "Googleの利用上限に達しました。しばらく待つか、キーの上限設定を確認してください。",
  INVALID_REQUEST: "検索条件が正しくありません。入力内容を確認してください。",
  UNKNOWN_ERROR: "Google側で一時的なエラーが発生しました。もう一度お試しください。",
};

function messageForStatus(status: string): string {
  return STATUS_MESSAGE[status] ?? `検索に失敗しました（${status}）。`;
}

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
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const accentClass = accent === "worker" ? "bg-worker" : "bg-client";

  const clearSuggestions = useCallback(() => setSuggestions([]), []);

  const emit = useCallback(
    (place: SearchedPlace) => {
      clearSuggestions();
      setMessage(null);
      onSelect(place);
    },
    [clearSuggestions, onSelect],
  );

  /** Geocoder によるテキスト検索。候補APIが使えない場合の最終手段。 */
  const searchByGeocoder = useCallback(
    (text: string) => {
      const maps = window.google?.maps;
      if (!maps) {
        setMessage("地図がまだ読み込まれていません。少し待ってからもう一度お試しください。");
        return;
      }
      setPending(true);
      setMessage(null);
      new maps.Geocoder().geocode(
        { address: text, language: "ja", region: "JP" },
        (results, status) => {
          setPending(false);
          const location = results?.[0]?.geometry?.location;
          if (status !== "OK" || !location) {
            setMessage(messageForStatus(status));
            return;
          }
          emit({
            lat: location.lat(),
            lng: location.lng(),
            address: results?.[0]?.formatted_address ?? text,
          });
        },
      );
    },
    [emit],
  );

  // 入力に応じて候補を取得する（Places が使えるときのみ。使えなければ候補なしで動く）
  useEffect(() => {
    const text = query.trim();
    if (text.length < MIN_QUERY_LENGTH) {
      clearSuggestions();
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      // window.google はスクリプト読み込み後に生えるため、毎回ここで参照する
      const places = window.google?.maps.places;
      if (!places) return;

      // 1. 新API
      if (places.AutocompleteSuggestion) {
        places.AutocompleteSuggestion.fetchAutocompleteSuggestions({
          input: text,
          language: "ja",
          includedRegionCodes: ["jp"],
        })
          .then(({ suggestions: fetched }) => {
            if (cancelled) return;
            const mapped: Suggestion[] = [];
            fetched.slice(0, MAX_SUGGESTIONS).forEach(({ placePrediction }, index) => {
              if (!placePrediction) return;
              const main = placePrediction.mainText?.text ?? placePrediction.text?.text ?? text;
              mapped.push({
                id: placePrediction.placeId ?? `new-${index}`,
                mainText: main,
                secondaryText: placePrediction.secondaryText?.text,
                place: placePrediction.toPlace?.(),
                fallbackQuery: placePrediction.text?.text ?? main,
              });
            });
            setSuggestions(mapped);
          })
          .catch(() => {
            // 新APIが使えない場合は候補なしで進む（確定時に Geocoder へ回す）
            if (!cancelled) clearSuggestions();
          });
        return;
      }

      // 2. 旧API
      if (places.AutocompleteService && places.PlacesServiceStatus) {
        const service = new places.AutocompleteService();
        service.getPlacePredictions(
          { input: text, language: "ja", componentRestrictions: { country: "jp" } },
          (results, status) => {
            if (cancelled) return;
            if (status !== places.PlacesServiceStatus?.OK || !results) {
              clearSuggestions();
              return;
            }
            setSuggestions(
              results.slice(0, MAX_SUGGESTIONS).map((prediction) => ({
                id: prediction.place_id,
                mainText: prediction.structured_formatting?.main_text ?? prediction.description,
                secondaryText: prediction.structured_formatting?.secondary_text,
                legacyPlaceId: prediction.place_id,
                fallbackQuery: prediction.description,
              })),
            );
          },
        );
      }
    }, DEBOUNCE_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, clearSuggestions]);

  // 候補の外側をタップしたら閉じる
  useEffect(() => {
    if (suggestions.length === 0) return;
    const handle = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) clearSuggestions();
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [suggestions.length, clearSuggestions]);

  const choose = async (suggestion: Suggestion) => {
    setQuery(suggestion.mainText);
    clearSuggestions();
    setPending(true);
    setMessage(null);

    // 新API: Place オブジェクトから座標を取得する
    if (suggestion.place) {
      try {
        const { place } = await suggestion.place.fetchFields({
          fields: ["location", "formattedAddress", "displayName"],
        });
        const location = place?.location ?? suggestion.place.location;
        if (location) {
          setPending(false);
          emit({
            lat: location.lat(),
            lng: location.lng(),
            address:
              place?.formattedAddress ?? place?.displayName ?? suggestion.fallbackQuery,
          });
          return;
        }
      } catch {
        // 座標が取れない場合はテキスト検索で救済する
      }
      setPending(false);
      searchByGeocoder(suggestion.fallbackQuery);
      return;
    }

    // 旧API: 詳細取得で座標を得る
    const places = window.google?.maps.places;
    if (suggestion.legacyPlaceId && places?.PlacesService && places.PlacesServiceStatus) {
      const service = new places.PlacesService(document.createElement("div"));
      service.getDetails(
        {
          placeId: suggestion.legacyPlaceId,
          fields: ["geometry", "formatted_address", "name"],
          language: "ja",
        },
        (place, status) => {
          setPending(false);
          const location = place?.geometry?.location;
          if (status !== places.PlacesServiceStatus?.OK || !location) {
            searchByGeocoder(suggestion.fallbackQuery);
            return;
          }
          emit({
            lat: location.lat(),
            lng: location.lng(),
            address: place?.formatted_address ?? place?.name ?? suggestion.fallbackQuery,
          });
        },
      );
      return;
    }

    setPending(false);
    searchByGeocoder(suggestion.fallbackQuery);
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const text = query.trim();
    if (text.length === 0) return;
    // 候補が出ていれば先頭を採用し、無ければテキスト検索する
    if (suggestions.length > 0) {
      void choose(suggestions[0]);
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

      {suggestions.length > 0 && (
        <ul className="absolute inset-x-0 top-full z-20 mt-1 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg">
          {suggestions.map((suggestion) => (
            <li key={suggestion.id}>
              <button
                type="button"
                onClick={() => void choose(suggestion)}
                className="block w-full px-3 py-2.5 text-left hover:bg-slate-50"
              >
                <span className="block text-sm text-slate-800">{suggestion.mainText}</span>
                {suggestion.secondaryText && (
                  <span className="block text-xs text-slate-500">{suggestion.secondaryText}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      {message && (
        <p className="mt-1 text-xs text-amber-700" role="alert">
          {message}
        </p>
      )}
    </div>
  );
}
