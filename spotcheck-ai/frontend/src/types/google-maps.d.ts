/**
 * Google Maps JavaScript API の最小限の型定義。
 * `@types/google.maps` を追加せずに、この画面で使う範囲だけを宣言する。
 */

export type LatLngLiteral = { lat: number; lng: number };

export interface GMap {
  setCenter(position: LatLngLiteral): void;
  setZoom(zoom: number): void;
  addListener(event: "click", handler: (event: { latLng?: GLatLng }) => void): void;
}

export interface GLatLng {
  lat(): number;
  lng(): number;
}

export interface GMarker {
  setPosition(position: LatLngLiteral): void;
  setMap(map: GMap | null): void;
  addListener(event: "click", handler: () => void): void;
}

export interface GeocoderResult {
  formatted_address: string;
  geometry?: { location: GLatLng };
}

/** Places Autocomplete の候補（必要な項目のみ）。 */
export interface GAutocompletePrediction {
  place_id: string;
  description: string;
  structured_formatting?: {
    main_text: string;
    secondary_text?: string;
  };
}

export interface GPlaceResult {
  formatted_address?: string;
  name?: string;
  geometry?: { location: GLatLng };
}

export interface GAutocompleteService {
  getPlacePredictions(
    request: {
      input: string;
      language?: string;
      componentRestrictions?: { country: string | string[] };
    },
    callback: (predictions: GAutocompletePrediction[] | null, status: string) => void,
  ): void;
}

export interface GPlacesService {
  getDetails(
    request: { placeId: string; fields?: string[]; language?: string },
    callback: (place: GPlaceResult | null, status: string) => void,
  ): void;
}

export interface GPlacesNamespace {
  AutocompleteService: new () => GAutocompleteService;
  PlacesService: new (attrContainer: HTMLElement | GMap) => GPlacesService;
  PlacesServiceStatus: { OK: string };
}

export interface GMapsNamespace {
  Map: new (
    element: HTMLElement,
    options: {
      center: LatLngLiteral;
      zoom: number;
      disableDefaultUI?: boolean;
      zoomControl?: boolean;
      clickableIcons?: boolean;
    },
  ) => GMap;
  Marker: new (options: {
    position: LatLngLiteral;
    map: GMap;
    title?: string;
    icon?: unknown;
  }) => GMarker;
  Geocoder: new () => {
    geocode(
      request: { location?: LatLngLiteral; address?: string; language?: string; region?: string },
      callback: (results: GeocoderResult[] | null, status: string) => void,
    ): void;
  };
  /** Places ライブラリ。APIキーで Places API が有効でない場合は undefined になりうる。 */
  places?: GPlacesNamespace;
}

declare global {
  interface Window {
    google?: { maps: GMapsNamespace };
    __spotcheckMapsLoader?: Promise<void>;
  }
}
