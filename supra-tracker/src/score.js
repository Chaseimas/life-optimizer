const { DONOR } = require('./config');

// Donor-fit scoring for a 2JZ-swap build: the chassis is what's being bought,
// the engine is getting replaced. Pure function - tweak weights freely, scores
// are computed live in the API and never stored.

// Positive phrases are stripped before negative checks so "no rust" can't
// count as a rust mention.
const POS_RX = /rust[- ]?free|no rust|zero rust|no rot\b|solid floors?|solid frame|solid underneath/g;
const STRUCT_WORDS = '(?:frame|rails?|rockers?|floors?|pans?|strut|towers?|quarters?|arch(?:es)?|hatch|underneath|undercarriage)';
const RUST_WORD = '(?:rust(?:y|ed)?|rot(?:ted|ten)?)';
const STRUCT_RX = new RegExp(`${STRUCT_WORDS}[^.]{0,40}?\\b${RUST_WORD}\\b|\\b${RUST_WORD}\\b[^.]{0,40}?${STRUCT_WORDS}`);
const COSM_RX = /surface rust|minor rust|light rust|little rust|rust bubbles?|bubbling/g;
const GENERIC_RX = new RegExp(`\\b${RUST_WORD}\\b`);
const DEAD_RX = /needs engine|no engine|engine out|no motor|blown|bad engine|knock|doesn'?t run|does not run|not running|won'?t start|roller\b/;
const COND_RX = [/garage kept|garaged/, /original paint/, /straight body/, /\b(one|1) owner/, /adult owned/, /always covered/, /(all|bone) stock/];

function scoreDonor(l) {
  const text = `${l.title || ''} ${l.snippet || ''} ${l.description || ''}`.toLowerCase();
  const reasons = [];
  const add = (delta, t) => reasons.push({ delta, text: t });

  // Price vs Phase-1 budget
  const p = l.price;
  if (p == null) add(-5, 'no price listed');
  else if (p < DONOR.budgetMin) add(5, "suspiciously cheap — verify it's real");
  else if (p <= DONOR.budgetMax) add(20, 'in Phase-1 budget');
  else if (p <= 12000) add(6, 'slightly over budget');
  else if (p <= 18000) add(-8, 'over budget');
  else add(-20, 'way over budget for a donor');

  // Rust (location-aware)
  if (POS_RX.test(text)) add(15, 'says rust-free / solid');
  POS_RX.lastIndex = 0;
  const neg = text.replace(POS_RX, ' ');
  const hasStruct = STRUCT_RX.test(neg);
  const hasCosm = COSM_RX.test(neg);
  COSM_RX.lastIndex = 0;
  const negNoCosm = neg.replace(COSM_RX, ' ');
  if (hasStruct) add(-25, 'structural rust (frame/rockers/floors area)');
  if (hasCosm) add(-6, 'cosmetic rust only');
  if (!hasStruct && !hasCosm && GENERIC_RX.test(negNoCosm)) add(-12, 'unspecified rust mentioned');

  // Title status
  if (/clean title/.test(text)) add(10, 'clean title');
  if (/salvage|rebuilt title|branded title|no title|bill of sale/.test(text)) add(-15, 'branded/missing title');

  // Condition positives, capped
  const condHits = COND_RX.filter((rx) => rx.test(text)).length;
  if (condHits > 0) add(Math.min(condHits * 5, 10), 'well-kept signals');

  // Dead engine = fine for a swap, if the price agrees
  if (/parts car|parting out/.test(text)) add(-15, 'parts car');
  else if (DEAD_RX.test(text)) {
    if (p != null && p <= DONOR.deadEngineCheapMax) add(12, "donor deal: cheap chassis, engine's getting swapped anyway");
    else if (p != null && p > DONOR.deadEngineHighMin) add(-8, 'not running but priced like a runner');
    else add(4, 'engine condition irrelevant for swap');
  }

  if (/frame damage|frame rot|bent frame|wrecked|accident|front end damage/.test(text)) add(-15, 'frame/accident damage mentioned');
  if (l.state && DONOR.dryStates.includes(l.state)) add(6, 'dry-climate car');
  if (l.turbo_status === 'non_turbo') add(4, "non-turbo = cheaper chassis, engine's going anyway");

  const score = Math.max(0, Math.min(100, 50 + reasons.reduce((s, r) => s + r.delta, 0)));
  const tier = score >= 70 ? 'great' : score >= 50 ? 'possible' : 'poor';
  reasons.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  return { score, tier, reasons };
}

module.exports = { scoreDonor };
