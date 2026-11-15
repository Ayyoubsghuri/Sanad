// Loaded first in every page of the Android app (MainActivity adds it to <head>).
// The interface calls the backend at http://127.0.0.1:8765 like on the PC; here those calls go to the app's Java engine
// through window.SanadNative.request(), and the answer comes back through window.__sanadReply().
(function () {
  if (!window.SanadNative) return;
  var API = "http://127.0.0.1:8765";
  var pending = {};
  var seq = 0;
  window.__sanadReply = function (id, status, body) {
    var done = pending[id];
    if (!done) return;
    delete pending[id];
    done(status, body);
  };
  var original = window.fetch.bind(window);
  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url.indexOf(API) !== 0) return original(input, init);
    init = init || {};
    var method = (init.method || (typeof input === "object" && input.method) || "GET").toUpperCase();
    var body = init.body;
    if (body != null && typeof body !== "string") body = ""; // uploads (FormData) are not supported on the phone
    return new Promise(function (resolve, reject) {
      var id = "r" + ++seq;
      var signal = init.signal;
      var abort = function () {
        delete pending[id];
        reject(new DOMException("The request was cancelled.", "AbortError"));
      };
      if (signal) {
        if (signal.aborted) return abort();
        signal.addEventListener("abort", abort);
      }
      pending[id] = function (status, text) {
        if (signal) signal.removeEventListener("abort", abort);
        resolve(new Response(status === 204 ? null : text, { status: status, headers: { "Content-Type": "application/json" } }));
      };
      window.SanadNative.request(id, method, url.slice(API.length), body || "");
    });
  };
})();
