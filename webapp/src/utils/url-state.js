// URL state encoder/decoder for shareable links.
//
// Format:
//   ?view=latam                            (default)
//   ?view=commune                          (in a city)
//   ?view=commune&city=santiago            (specific city)
//   ?view=commune&city=santiago&commune=lo_espejo
//   ?view=commune&city=santiago&exposome=pm25
//   ?view=commune&city=santiago&commune=lo_espejo&exposome=pm25&tab=fuente
//   ?view=commune&city=santiago&loc=-70.650000,-33.450000
//   ?view=commune&city=santiago&zip=8320000&loc=-70.650000,-33.450000

const DEFAULTS = {
  view: "latam",
  city: null,
  commune: null,
  exposome: "pm25",
  tab: "exposome",
  loc: null,
  zip: null,
};

export function getInitialState() {
  const params = new URLSearchParams(window.location.search);
  return {
    view: params.get("view") || DEFAULTS.view,
    city: params.get("city"),
    commune: params.get("commune"),
    exposome: params.get("exposome") || DEFAULTS.exposome,
    tab: params.get("tab") || DEFAULTS.tab,
    loc: params.get("loc"),
    zip: params.get("zip"),
  };
}

export function encodeState(state) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(state)) {
    if (v !== null && v !== undefined && v !== DEFAULTS[k]) {
      params.set(k, v);
    }
  }
  const qs = params.toString();
  const url = qs
    ? `${window.location.pathname}?${qs}`
    : window.location.pathname;
  return url;
}

export function setURLState(state, replace = true) {
  const url = encodeState(state);
  if (replace) {
    window.history.replaceState(state, "", url);
  } else {
    window.history.pushState(state, "", url);
  }
}

export function onPopState(handler) {
  window.addEventListener("popstate", (e) => {
    if (e.state) handler(e.state);
  });
}
