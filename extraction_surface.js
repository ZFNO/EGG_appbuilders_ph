/* Extraction surface (ES5, offline, no CDN). Shared by BUILDER + LEAD runtime spike.
   IN: raw text -> {name, amount, date}. Self-hosted wllama/Transformers.js OUT of this file (mock extractor).
   Receipt = hash/append-log only. Car sensor-only. Airplane mode OK. */
var ExtractionSurface = (function () {
  function pad(n) { return n < 10 ? '0' + n : '' + n; }

  // Mock local model: deterministic field extraction (name/amount/date)
  function extract(text) {
    var out = { name: null, amount: null, date: null };
    if (!text) return out;
    var amt = text.match(/(?:php|p|₱|\s)?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)/i);
    var dt = text.match(/(\d{1,4}[-\/]\d{1,2}[-\/]\d{1,4})/);
    var nm = text.match(/(?:from|to|payee|name)\s*[:\-]?\s*([A-Za-z .'-]{2,40})/i);
    if (amt) out.amount = amt[1];
    if (dt) out.date = dt[1];
    if (nm) out.name = nm[1].replace(/\s+$/, '');
    return out;
  }

  // FNV-1a hash for receipt id (no crypto, no network)
  function hash(s) {
    var h = 0x811c9dc5, i;
    for (i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = (h * 0x01000193) >>> 0; }
    return ('0000000' + h.toString(16)).slice(-8);
  }

  function makeReceipt(text) {
    var f = extract(text);
    var body = (f.name || '') + '|' + (f.amount || '') + '|' + (f.date || '');
    return { fields: f, id: hash(body), ts: Date.now(), log: 'append' };
  }

  return { extract: extract, hash: hash, makeReceipt: makeReceipt };
})();
