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

// ----------------------------------------------------------------------
// ストリートビュー
// ----------------------------------------------------------------------
export interface GStreetViewLocation {
  latLng?: GLatLng | null;
  description?: string | null;
}

export interface GStreetViewPanoramaData {
  location?: GStreetViewLocation | null;
}

export interface GStreetViewPanorama {
  setPosition(position: LatLngLiteral): void;
  setPov(pov: { heading: number; pitch: number }): void;
  setVisible(visible: boolean): void;
  getPosition(): GLatLng | null;
  addListener(event: "position_changed", handler: () => void): void;
}

export interface GStreetViewService {
  /** 指定地点の近くにパノラマがあるか調べる。無ければ status が "ZERO_RESULTS"。 */
  getPanorama(
    request: { location: LatLngLiteral; radius?: number },
    callback: (data: GStreetViewPanoramaData | null, status: string) => void,
  ): void;
}

export interface GeocoderResult {
  formatted_address: string;
  geometry?: { location: GLatLng };
}

// ----------------------------------------------------------------------
// Places（新API）
// ----------------------------------------------------------------------
/** `AutocompleteSuggestion.fetchAutocompleteSuggestions()` が返す候補。 */
export interface GPlacePrediction {
  placeId?: string;
  text?: { text: string };
  mainText?: { text: string };
  secondaryText?: { text: string };
  toPlace?: () => GPlaceNew;
}

export interface GAutocompleteSuggestionNew {
  placePrediction?: GPlacePrediction | null;
}

/** 新APIの Place オブジェクト（必要なフィールドのみ）。 */
export interface GPlaceNew {
  id?: string;
  displayName?: string | null;
  formattedAddress?: string | null;
  location?: GLatLng | null;
  fetchFields(request: { fields: string[] }): Promise<{ place?: GPlaceNew }>;
}

// ----------------------------------------------------------------------
// Places（旧API）
// ----------------------------------------------------------------------
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
  /** 新API。Places API (New) が有効なときに使える。 */
  AutocompleteSuggestion?: {
    fetchAutocompleteSuggestions(request: {
      input: string;
      language?: string;
      includedRegionCodes?: string[];
    }): Promise<{ suggestions: GAutocompleteSuggestionNew[] }>;
  };
  /** 旧API。レガシーAPIが有効なプロジェクトでのみ使える。 */
  AutocompleteService?: new () => GAutocompleteService;
  PlacesService?: new (attrContainer: HTMLElement | GMap) => GPlacesService;
  PlacesServiceStatus?: { OK: string };
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
  /** Places ライブラリ。Places API が有効でない場合は undefined になりうる。 */
  places?: GPlacesNamespace;
  StreetViewPanorama: new (
    element: HTMLElement,
    options: {
      position: LatLngLiteral;
      pov?: { heading: number; pitch: number };
      zoom?: number;
      disableDefaultUI?: boolean;
      addressControl?: boolean;
      linksControl?: boolean;
      panControl?: boolean;
      zoomControl?: boolean;
      fullscreenControl?: boolean;
      motionTracking?: boolean;
      motionTrackingControl?: boolean;
    },
  ) => GStreetViewPanorama;
  StreetViewService: new () => GStreetViewService;
  StreetViewStatus: { OK: string; ZERO_RESULTS: string; UNKNOWN_ERROR: string };
}

declare global {
  interface Window {
    google?: { maps: GMapsNamespace };
    __spotcheckMapsLoader?: Promise<void>;
  }
}
