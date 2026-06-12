// Kase's MK3 Supra cyberpunk 1000HP build plan (2026-06). Display data only.
module.exports = {
  phases: [
    { n: 1, name: 'Buy the Car', goal: 'Clean MK3 Supra chassis', items: [
      { item: 'Clean MK3 Supra', cost: '$8k–$20k', install: '—' },
      { item: 'Registration/title/tax', cost: '$500–$2k', install: '—' },
    ], totals: { running: '$8.5k–$22k' } },
    { n: 2, name: 'Reliability', goal: 'Keep stock engine for now', items: [
      { item: 'Full fluid service', cost: '$200–$500', install: '$150–$400' },
      { item: 'Timing belt/water pump', cost: '$300–$700', install: '$500–$1k' },
      { item: 'Aluminum radiator', cost: '$250–$500', install: '$150–$400' },
      { item: 'Brakes + rotors', cost: '$400–$1k', install: '$300–$700' },
      { item: 'Bushings/wheel bearings', cost: '$400–$1.2k', install: '$500–$1.5k' },
      { item: 'Coilovers (temporary)', cost: '$800–$2k', install: '$300–$700' },
      { item: 'Wheels + tires', cost: '$2k–$5k', install: '$100–$300' },
    ], totals: { parts: '$4.3k–$10.9k', install: '$2k–$5k' } },
    { n: 3, name: 'Cyberpunk Lighting', items: [
      { item: 'RGB halos', cost: '$150–$400', install: '$200–$500' },
      { item: 'RGB demon eyes', cost: '$100–$300', install: '$200–$500' },
      { item: 'RGB controller/app setup', cost: '$50–$150', install: 'Included' },
      { item: 'Pink underglow kit', cost: '$100–$300', install: '$150–$500' },
      { item: 'Interior ambient lighting', cost: '$100–$500', install: '$200–$800' },
      { item: 'Smoked tails/headlights', cost: '$100–$400', install: '$50–$200' },
    ], totals: { parts: '$600–$2k', install: '$600–$2.5k' } },
    { n: 4, name: 'Air Suspension', items: [
      { item: 'Air Lift Performance kit', cost: '$3k–$5k', install: '$1k–$2.5k' },
      { item: 'AccuAir management', cost: '$1.5k–$3k', install: 'Included' },
      { item: 'Compressors/tank/lines', cost: '$800–$2k', install: '$500–$1.5k' },
    ], totals: { parts: '$5.3k–$10k', install: '$1.5k–$4k' } },
    { n: 5, name: 'Power Support Mods', items: [
      { item: 'Big brake kit', cost: '$2k–$6k', install: '$300–$800' },
      { item: 'Fuel system', cost: '$1.5k–$4k', install: '$800–$2k' },
      { item: 'Oil cooler', cost: '$300–$800', install: '$200–$600' },
      { item: 'Electric fans', cost: '$200–$500', install: '$100–$300' },
      { item: 'Differential upgrade', cost: '$1k–$3k', install: '$500–$1.5k' },
    ], totals: { parts: '$5k–$14k', install: '$2k–$5k' } },
    { n: 6, name: 'Buy Complete 2JZ Swap', items: [
      { item: '2JZ-GTE engine', cost: '$5k–$12k', install: '—' },
      { item: 'Transmission (CD009/T56/TH400)', cost: '$2k–$8k', install: '—' },
      { item: 'Swap harness/ECU', cost: '$2k–$5k', install: '—' },
      { item: 'Swap mounts/driveshaft', cost: '$1k–$3k', install: '—' },
    ], totals: { parts: '$10k–$28k' } },
    { n: 7, name: 'Engine Swap + Big Turbo', items: [
      { item: 'Single turbo kit', cost: '$4k–$10k', install: '$1k–$3k' },
      { item: 'Intercooler setup', cost: '$800–$2k', install: '$300–$1k' },
      { item: 'Exhaust', cost: '$1k–$3k', install: '$300–$800' },
      { item: 'Standalone ECU tune', cost: '$1k–$3k', install: '$1k–$2k' },
      { item: 'Swap labor', cost: '—', install: '$5k–$15k' },
    ], totals: { parts: '$6.8k–$18k', install: '$7.6k–$21k' } },
    { n: 8, name: 'Widebody + Final Look', items: [
      { item: 'Widebody kit', cost: '$2k–$8k', install: '$2k–$8k' },
      { item: 'Paint/wrap', cost: '$4k–$15k', install: 'Included' },
      { item: 'Splitter/diffuser', cost: '$500–$3k', install: '$300–$1k' },
      { item: 'Final wheels/fitment', cost: '$2k–$6k', install: '$100–$300' },
    ], totals: { parts: '$8.5k–$32k', install: '$2.4k–$9k' } },
    { n: 9, name: 'True 1000HP Build', items: [
      { item: 'Forged internals', cost: '$4k–$10k', install: '$3k–$8k' },
      { item: 'Bigger turbo', cost: '$2k–$5k', install: '$500–$1.5k' },
      { item: 'E85 conversion', cost: '$500–$2k', install: '$300–$800' },
      { item: 'Dyno tuning', cost: '$800–$2k', install: 'Included' },
    ], totals: { parts: '$7.3k–$19k', install: '$3.8k–$10k' } },
  ],
  finals: [
    { level: 'DIY-heavy build', total: '$40k–$60k' },
    { level: 'Balanced realistic build', total: '$60k–$90k' },
    { level: 'High-end professional show build', total: '$100k–$150k+' },
  ],
  note: 'Tracker donor budget is set to $1k–$9k for the Phase-1 chassis (scored, never filtered).',
};
