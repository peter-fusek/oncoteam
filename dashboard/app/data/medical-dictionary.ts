export interface DictionaryEntry {
  abbr: string
  fullName: { sk: string; en: string }
  proDesc: { sk: string; en: string }
  laikDesc: { sk: string; en: string }
  category: 'lab' | 'tumor_marker' | 'treatment' | 'diagnosis' | 'inflammation' | 'general' | 'toxicity'
  unit?: string
  referenceRange?: string
}

export const MEDICAL_DICTIONARY: DictionaryEntry[] = [
  // ── Lab / CBC ──
  {
    abbr: 'ANC',
    fullName: { sk: 'Absolútny počet neutrofilov', en: 'Absolute Neutrophil Count' },
    proDesc: {
      sk: 'Kľúčový parameter pre rozhodnutie o podaní chemoterapie. ANC < 1500/µL = odložiť cyklus. ANC < 500 = febrilná neutropénia.',
      en: 'Key parameter for chemotherapy go/no-go. ANC < 1500/µL = hold cycle. ANC < 500 = febrile neutropenia risk.',
    },
    laikDesc: {
      sk: 'Počet bielych krviniek, ktoré bojujú s infekciami. Ak je nízky, chemoterapia sa odloží, kým sa hodnota nevráti do normy.',
      en: 'Count of white blood cells that fight infections. If too low, chemo is delayed until it recovers.',
    },
    category: 'lab',
    unit: '/µL',
    referenceRange: '1,800–7,700',
  },
  {
    abbr: 'WBC',
    fullName: { sk: 'Leukocyty (biele krvinky)', en: 'White Blood Cell Count' },
    proDesc: {
      sk: 'Celkový počet leukocytov. Leukopénia < 4.0, leukocytóza > 11.0. Sleduje sa pred každým cyklom.',
      en: 'Total leukocyte count. Leukopenia < 4.0, leukocytosis > 11.0. Monitored before each cycle.',
    },
    laikDesc: {
      sk: 'Celkový počet bielych krviniek v krvi. Ukazuje, ako dobre funguje imunitný systém.',
      en: 'Total white blood cells in your blood. Shows how well your immune system is working.',
    },
    category: 'lab',
    unit: '×10³/µL',
    referenceRange: '4.5–11.0',
  },
  {
    abbr: 'PLT',
    fullName: { sk: 'Trombocyty (krvné doštičky)', en: 'Platelet Count' },
    proDesc: {
      sk: 'Trombocytopénia < 75 000 = odložiť chemo. Pri antikoagulácii (Clexane) PLT < 50 000 = konzultácia hematológ.',
      en: 'Thrombocytopenia < 75,000 = hold chemo. With anticoagulation (Clexane) PLT < 50,000 = hematology consult.',
    },
    laikDesc: {
      sk: 'Krvné doštičky pomáhajú zrážaniu krvi. Ak sú príliš nízke, zvyšuje sa riziko krvácania.',
      en: 'Platelets help your blood clot. If too low, there is a higher risk of bleeding.',
    },
    category: 'lab',
    unit: '/µL',
    referenceRange: '150,000–400,000',
  },
  {
    abbr: 'HGB',
    fullName: { sk: 'Hemoglobín', en: 'Hemoglobin' },
    proDesc: {
      sk: 'Anémia: mierna < 12 g/dL, stredná < 10, ťažká < 8. Zvážiť transfúziu pri HGB < 7-8 alebo symptomatickej anémii.',
      en: 'Anemia grading: mild < 12 g/dL, moderate < 10, severe < 8. Consider transfusion at HGB < 7-8 or symptomatic.',
    },
    laikDesc: {
      sk: 'Ukazuje, koľko kyslíka dokáže krv prenášať. Nízka hodnota znamená únavu a slabosť.',
      en: 'Shows how much oxygen your blood can carry. Low levels cause tiredness and weakness.',
    },
    category: 'lab',
    unit: 'g/dL',
    referenceRange: '12.0–16.0',
  },
  {
    abbr: 'ABS_LYMPH',
    fullName: { sk: 'Absolútny počet lymfocytov', en: 'Absolute Lymphocyte Count' },
    proDesc: {
      sk: 'Lymfopénia < 1000/µL. Dôležitý pre výpočet Ne/Ly ratio a SII. Prognostický marker pri mCRC.',
      en: 'Lymphopenia < 1000/µL. Key for Ne/Ly ratio and SII calculation. Prognostic marker in mCRC.',
    },
    laikDesc: {
      sk: 'Typ bielych krviniek dôležitý pre imunitu. Pomáha lekárom hodnotiť celkový stav imunitného systému.',
      en: 'A type of white blood cell important for immunity. Helps doctors assess your overall immune health.',
    },
    category: 'lab',
    unit: '/µL',
    referenceRange: '1,000–4,800',
  },

  // ── Tumor Markers ──
  {
    abbr: 'CEA',
    fullName: { sk: 'Karcinoembryonálny antigén', en: 'Carcinoembryonic Antigen' },
    proDesc: {
      sk: 'Primárny nádorový marker pre CRC. Sleduje sa pred každým cyklom. Pokles > 50% po 1. cykle = priaznivá odpoveď. Stúpanie = možná progresia.',
      en: 'Primary tumor marker for CRC. Monitored before each cycle. > 50% decline after C1 = favorable response. Rising = possible progression.',
    },
    laikDesc: {
      sk: 'Látka v krvi, ktorú môže produkovať nádor. Lekári sledujú, či klesá (liečba funguje) alebo stúpa (nádor rastie).',
      en: 'A substance in blood that tumors can produce. Doctors track if it drops (treatment working) or rises (tumor growing).',
    },
    category: 'tumor_marker',
    unit: 'ng/mL',
    referenceRange: '0–5',
  },
  {
    abbr: 'CA 19-9',
    fullName: { sk: 'Karbohydrátový antigén 19-9', en: 'Carbohydrate Antigen 19-9' },
    proDesc: {
      sk: 'Sekundárny marker pre CRC, primárny pre pankreatický karcinóm. Zvýšené hodnoty korelujú s nádorovou záťažou.',
      en: 'Secondary marker for CRC, primary for pancreatic cancer. Elevated levels correlate with tumor burden.',
    },
    laikDesc: {
      sk: 'Ďalšia látka v krvi spojená s nádorom. Sleduje sa spolu s CEA pre lepší prehľad o priebehu liečby.',
      en: 'Another blood substance linked to tumors. Tracked alongside CEA for a better picture of treatment progress.',
    },
    category: 'tumor_marker',
    unit: 'U/mL',
    referenceRange: '0–37',
  },

  // ── Liver / Kidney ──
  {
    abbr: 'ALT',
    fullName: { sk: 'Alanínaminotransferáza', en: 'Alanine Aminotransferase' },
    proDesc: {
      sk: 'Hepatocelulárny marker. ALT > 5× ULN = odložiť chemo (pri hepatálnych metastázach vyššia tolerancia).',
      en: 'Hepatocellular marker. ALT > 5× ULN = hold chemo (higher tolerance with liver mets).',
    },
    laikDesc: {
      sk: 'Enzým z pečene. Vysoké hodnoty naznačujú, že pečeň môže byť zaťažená liečbou alebo metastázami.',
      en: 'A liver enzyme. High levels suggest the liver may be stressed by treatment or metastases.',
    },
    category: 'lab',
    unit: 'U/L',
    referenceRange: '0–35',
  },
  {
    abbr: 'AST',
    fullName: { sk: 'Aspartátaminotransferáza', en: 'Aspartate Aminotransferase' },
    proDesc: {
      sk: 'Hepatocelulárny marker, menej špecifický ako ALT (aj svalový pôvod). Sleduje sa spolu s ALT.',
      en: 'Hepatocellular marker, less specific than ALT (also muscle origin). Monitored alongside ALT.',
    },
    laikDesc: {
      sk: 'Enzým z pečene a svalov. Spolu s ALT ukazuje, ako pečeň zvláda liečbu.',
      en: 'An enzyme from the liver and muscles. Together with ALT, shows how the liver handles treatment.',
    },
    category: 'lab',
    unit: 'U/L',
    referenceRange: '0–35',
  },
  {
    abbr: 'Creatinine',
    fullName: { sk: 'Kreatinín', en: 'Creatinine' },
    proDesc: {
      sk: 'Marker funkcie obličiek. Kreatinín > 1.5× ULN = odložiť chemoterapiu. Dôležité pred oxaliplatinou.',
      en: 'Kidney function marker. Creatinine > 1.5× ULN = hold chemo. Important before oxaliplatin.',
    },
    laikDesc: {
      sk: 'Ukazuje, ako dobre pracujú obličky. Pred chemoterapiou sa kontroluje, či obličky zvládnu liečbu.',
      en: 'Shows how well your kidneys are working. Checked before chemo to ensure kidneys can handle treatment.',
    },
    category: 'lab',
    unit: 'mg/dL',
    referenceRange: '0.6–1.1',
  },
  {
    abbr: 'Bilirubin',
    fullName: { sk: 'Bilirubín', en: 'Bilirubin' },
    proDesc: {
      sk: 'Marker cholestázy. Bilirubín > 1.5× ULN = odložiť chemo. Zvýšenie + GMT/ALP = cholestáza (metastázy?).',
      en: 'Cholestasis marker. Bilirubin > 1.5× ULN = hold chemo. Elevation + GMT/ALP = cholestasis (mets?).',
    },
    laikDesc: {
      sk: 'Žltý pigment z rozpadu červených krviniek. Vysoké hodnoty môžu naznačovať problémy s pečeňou.',
      en: 'Yellow pigment from red blood cell breakdown. High levels may indicate liver problems.',
    },
    category: 'lab',
    unit: 'mg/dL',
    referenceRange: '0.1–1.2',
  },

  // ── Inflammation Indices ──
  {
    abbr: 'SII',
    fullName: { sk: 'Systémový imunitno-zápalový index', en: 'Systemic Immune-Inflammation Index' },
    proDesc: {
      sk: 'SII = (ABS_NEUT × PLT) / ABS_LYMPH. > 1800 = vysoká zápalová záťaž. > 30% pokles po C1 = priaznivé.',
      en: 'SII = (ABS_NEUT × PLT) / ABS_LYMPH. > 1800 = high inflammatory burden. > 30% decline after C1 = favorable.',
    },
    laikDesc: {
      sk: 'Číslo vypočítané z krvného obrazu, ktoré ukazuje úroveň zápalu v tele. Nižšie = lepšie.',
      en: 'A number calculated from blood counts showing inflammation level. Lower = better.',
    },
    category: 'inflammation',
    referenceRange: '0–1,800',
  },
  {
    abbr: 'Ne/Ly',
    fullName: { sk: 'Pomer neutrofilov k lymfocytom', en: 'Neutrophil-to-Lymphocyte Ratio' },
    proDesc: {
      sk: 'Ne/Ly > 3.0 = nepriaznivá prognóza. Ne/Ly < 2.5 = zlepšenie. Prognostický biomarker v onkológii.',
      en: 'Ne/Ly > 3.0 = poor prognosis. Ne/Ly < 2.5 = improving. Prognostic biomarker in oncology.',
    },
    laikDesc: {
      sk: 'Pomer dvoch typov bielych krviniek. Pomáha lekárom odhadnúť, ako telo reaguje na liečbu.',
      en: 'Ratio of two types of white blood cells. Helps doctors estimate how the body responds to treatment.',
    },
    category: 'inflammation',
    referenceRange: '0–3.0',
  },

  // ── Biomarkers / Genetics ──
  {
    abbr: 'KRAS',
    fullName: { sk: 'Kirsten Rat Sarcoma vírusový onkogén', en: 'Kirsten Rat Sarcoma Viral Oncogene' },
    proDesc: {
      sk: 'Mutácie KRAS (G12, G13, Q61) vylučujú anti-EGFR liečbu. G12C má špecifické inhibítory (sotorasib). G12S nemá cielený liek.',
      en: 'KRAS mutations (G12, G13, Q61) exclude anti-EGFR therapy. G12C has specific inhibitors (sotorasib). G12S has no targeted drug.',
    },
    laikDesc: {
      sk: 'Gén, ktorý môže byť zmutovaný v nádore. Mutácia ovplyvňuje, aká liečba je vhodná.',
      en: 'A gene that may be mutated in the tumor. The mutation affects which treatments will work.',
    },
    category: 'diagnosis',
  },
  {
    abbr: 'MSI',
    fullName: { sk: 'Mikrosatelitová instabilita', en: 'Microsatellite Instability' },
    proDesc: {
      sk: 'MSI-H/dMMR = imunoterapia účinná (pembrolizumab). MSS/pMMR = checkpoint monoterapia neindikovaná.',
      en: 'MSI-H/dMMR = immunotherapy effective (pembrolizumab). MSS/pMMR = checkpoint monotherapy not indicated.',
    },
    laikDesc: {
      sk: 'Test DNA nádoru. Výsledok rozhoduje, či je vhodná imunoterapia (liečba, ktorá pomáha imunite bojovať s nádorom).',
      en: 'A DNA test on the tumor. The result determines if immunotherapy (which helps your immune system fight cancer) will work.',
    },
    category: 'diagnosis',
  },
  {
    abbr: 'HER2',
    fullName: { sk: 'Receptor ľudského epidermálneho rastového faktora 2', en: 'Human Epidermal Growth Factor Receptor 2' },
    proDesc: {
      sk: 'HER2+ mCRC: trastuzumab + pertuzumab alebo T-DXd. HER2 negatívny: HER2-cielená liečba nie je indikovaná.',
      en: 'HER2+ mCRC: trastuzumab + pertuzumab or T-DXd. HER2 negative: HER2-targeted therapy not indicated.',
    },
    laikDesc: {
      sk: 'Proteín na povrchu nádorových buniek. Ak je prítomný vo veľkom množstve, existujú špeciálne lieky.',
      en: 'A protein on tumor cell surfaces. If present in large amounts, special drugs can target it.',
    },
    category: 'diagnosis',
  },

  // ── Treatment ──
  {
    abbr: 'mFOLFOX6',
    fullName: { sk: 'Modifikovaný FOLFOX6 protokol', en: 'Modified FOLFOX6 Protocol' },
    proDesc: {
      sk: '5-FU + leucovorín + oxaliplatina. Štandard 1. línie pre mCRC. Cyklus 14 dní, max 12 cyklov (kumulatívna neurotoxicita).',
      en: '5-FU + leucovorin + oxaliplatin. Standard 1st-line for mCRC. 14-day cycle, max 12 cycles (cumulative neurotoxicity).',
    },
    laikDesc: {
      sk: 'Kombinácia troch liekov podávaná každé 2 týždne. Hlavná liečba metastatického kolorektálneho karcinómu.',
      en: 'A combination of three drugs given every 2 weeks. The main treatment for metastatic colorectal cancer.',
    },
    category: 'treatment',
  },
  {
    abbr: 'ECOG',
    fullName: { sk: 'Výkonnostný stav ECOG', en: 'ECOG Performance Status' },
    proDesc: {
      sk: '0 = plne aktívny, 1 = obmedzená fyzická aktivita, 2 = sebestačný ale neschopný práce, 3 = obmedzená sebestačnosť, 4 = pripútaný na lôžko.',
      en: '0 = fully active, 1 = restricted physical activity, 2 = ambulatory but unable to work, 3 = limited self-care, 4 = bedridden.',
    },
    laikDesc: {
      sk: 'Škála od 0 do 4, ktorá hodnotí, ako dobre pacient zvláda bežné denné aktivity.',
      en: 'A scale from 0 to 4 rating how well a patient handles daily activities.',
    },
    category: 'general',
  },
  {
    abbr: 'CTCAE',
    fullName: { sk: 'Spoločné kritériá pre nežiaduce účinky', en: 'Common Terminology Criteria for Adverse Events' },
    proDesc: {
      sk: 'NCI-CTCAE v5.0. Stupnica 1-5 pre závažnosť toxicity. G1 = mierna, G2 = stredná, G3 = závažná, G4 = život ohrozujúca, G5 = smrť.',
      en: 'NCI-CTCAE v5.0. Grades 1-5 for toxicity severity. G1 = mild, G2 = moderate, G3 = severe, G4 = life-threatening, G5 = death.',
    },
    laikDesc: {
      sk: 'Systém hodnotenia vedľajších účinkov liečby od miernych (stupeň 1) po veľmi závažné (stupeň 4-5).',
      en: 'A system for rating treatment side effects from mild (grade 1) to very serious (grade 4-5).',
    },
    category: 'general',
  },
  {
    abbr: 'VTE',
    fullName: { sk: 'Venózny tromboembolizmus', en: 'Venous Thromboembolism' },
    proDesc: {
      sk: 'Zahŕňa DVT a PE. Pri aktívnej VTE: antikoagulácia povinná. Bevacizumab vysoké riziko. Checkpoint inhibítory kompatibilné.',
      en: 'Includes DVT and PE. With active VTE: anticoagulation mandatory. Bevacizumab high risk. Checkpoint inhibitors compatible.',
    },
    laikDesc: {
      sk: 'Krvné zrazeniny v žilách. Pacient musí dostávať injekcie na riedenie krvi (Clexane) a niektoré lieky sú rizikové.',
      en: 'Blood clots in veins. Patient must receive blood-thinning injections (Clexane) and some drugs carry higher risk.',
    },
    category: 'general',
  },
  {
    abbr: 'RECIST',
    fullName: { sk: 'Kritériá hodnotenia odpovede', en: 'Response Evaluation Criteria in Solid Tumors' },
    proDesc: {
      sk: 'RECIST 1.1: CR = kompletná odpoveď, PR = parciálna (≥30% zmenšenie), SD = stabilizácia, PD = progresia (≥20% zväčšenie).',
      en: 'RECIST 1.1: CR = complete response, PR = partial (≥30% decrease), SD = stable disease, PD = progressive (≥20% increase).',
    },
    laikDesc: {
      sk: 'Spôsob merania, či sa nádor zmenšuje, je stabilný, alebo rastie na základe CT vyšetrení.',
      en: 'A way to measure whether the tumor is shrinking, stable, or growing based on CT scans.',
    },
    category: 'general',
  },
  {
    abbr: 'mCRC',
    fullName: { sk: 'Metastatický kolorektálny karcinóm', en: 'Metastatic Colorectal Cancer' },
    proDesc: {
      sk: 'CRC štádium IV s vzdialenými metastázami (pečeň, pľúca, peritoneum). Liečba: systémová chemoterapia ± biologická liečba.',
      en: 'CRC stage IV with distant metastases (liver, lungs, peritoneum). Treatment: systemic chemo ± targeted therapy.',
    },
    laikDesc: {
      sk: 'Rakovina hrubého čreva, ktorá sa rozšírila do iných častí tela. Liečí sa kombináciou liekov.',
      en: 'Colon cancer that has spread to other parts of the body. Treated with a combination of drugs.',
    },
    category: 'diagnosis',
  },

  // ── Additional Lab Values ──
  {
    abbr: 'ALP',
    fullName: { sk: 'Alkalická fosfatáza', en: 'Alkaline Phosphatase' },
    proDesc: {
      sk: 'Cholestáza: ALP + GMT zvýšené = obštrukcia žlčových ciest. Pri hepatálnych metastázach často elevovaná.',
      en: 'Cholestasis: ALP + GMT elevated = bile duct obstruction. Often elevated with liver metastases.',
    },
    laikDesc: {
      sk: 'Enzým z pečene a kostí. Vysoké hodnoty môžu naznačovať problémy so žlčovými cestami.',
      en: 'An enzyme from the liver and bones. High levels may indicate bile duct issues.',
    },
    category: 'lab',
    unit: 'U/L',
    referenceRange: '44–147',
  },
  {
    abbr: 'GMT',
    fullName: { sk: 'Gama-glutamyltransferáza', en: 'Gamma-Glutamyl Transferase' },
    proDesc: {
      sk: 'Citlivý marker cholestázy a hepatotoxicity. GMT + ALP zvýšené = cholestáza. GMT izolovaná = lieky, alkohol.',
      en: 'Sensitive cholestasis and hepatotoxicity marker. GMT + ALP elevated = cholestasis. Isolated GMT = drugs, alcohol.',
    },
    laikDesc: {
      sk: 'Pečeňový enzým. Pomáha lekárom rozlíšiť typ poškodenia pečene.',
      en: 'A liver enzyme. Helps doctors distinguish the type of liver damage.',
    },
    category: 'lab',
    unit: 'U/L',
    referenceRange: '0–55',
  },
  {
    abbr: 'eGFR',
    fullName: { sk: 'Odhadovaná glomerulárna filtrácia', en: 'Estimated Glomerular Filtration Rate' },
    proDesc: {
      sk: 'KDIGO klasifikácia: >90 = normálna, 60-89 = mierne znížená, 30-59 = stredne, <30 = ťažko. Dôležité pred platinou.',
      en: 'KDIGO classification: >90 = normal, 60-89 = mildly decreased, 30-59 = moderate, <30 = severe. Important before platinum.',
    },
    laikDesc: {
      sk: 'Ukazuje, ako dobre obličky filtrujú krv. Dôležité pred podaním chemoterapie.',
      en: 'Shows how well kidneys filter blood. Important before administering chemotherapy.',
    },
    category: 'lab',
    unit: 'mL/min/1.73m²',
    referenceRange: '>90',
  },

  // ── Toxicity Terms ──
  {
    abbr: 'Neuropathy',
    fullName: { sk: 'Periférna neuropatia', en: 'Peripheral Neuropathy' },
    proDesc: {
      sk: 'Oxaliplatina: akútna (chlad, hrdlo) a kumulatívna (prsty, nohy). G2 = znížiť dávku, G3 = vysadiť oxaliplatinu.',
      en: 'Oxaliplatin: acute (cold, throat) and cumulative (fingers, feet). G2 = reduce dose, G3 = discontinue oxaliplatin.',
    },
    laikDesc: {
      sk: 'Tŕpnutie alebo bolesť v prstoch rúk a nôh spôsobená chemoterapiou. Môže sa zhoršovať s každým cyklom.',
      en: 'Tingling or pain in fingers and toes caused by chemo. Can worsen with each cycle.',
    },
    category: 'toxicity',
  },
  {
    abbr: 'Diarrhea',
    fullName: { sk: 'Hnačka (chemoterapiou indukovaná)', en: 'Chemotherapy-Induced Diarrhea' },
    proDesc: {
      sk: '5-FU a irinotekan: G1-2 = loperamid, G3 = odložiť cyklus + i.v. hydratácia, G4 = hospitalizácia.',
      en: '5-FU and irinotecan: G1-2 = loperamide, G3 = delay cycle + IV hydration, G4 = hospitalization.',
    },
    laikDesc: {
      sk: 'Častý vedľajší účinok chemoterapie. Pri závažných prípadoch sa liečba pozastaví.',
      en: 'Common chemo side effect. In severe cases, treatment is paused.',
    },
    category: 'toxicity',
  },
  {
    abbr: 'Mucositis',
    fullName: { sk: 'Mukozitída', en: 'Oral Mucositis' },
    proDesc: {
      sk: '5-FU: zápal slizníc úst. G1-2 = lokálna liečba, G3 = odložiť cyklus, znížiť 5-FU.',
      en: '5-FU: oral mucosa inflammation. G1-2 = topical treatment, G3 = delay cycle, reduce 5-FU.',
    },
    laikDesc: {
      sk: 'Bolestivé vredy v ústach spôsobené chemoterapiou. Pri ťažších prípadoch sa upraví dávka.',
      en: 'Painful mouth sores caused by chemo. In severe cases, the dose is adjusted.',
    },
    category: 'toxicity',
  },
  {
    abbr: 'HFS',
    fullName: { sk: 'Hand-foot syndróm', en: 'Hand-Foot Syndrome' },
    proDesc: {
      sk: 'Palmoplantárna erytrodyzestézia. 5-FU, kapecitabín. G2 = znížiť dávku, G3 = prerušiť liečbu.',
      en: 'Palmar-plantar erythrodysesthesia. 5-FU, capecitabine. G2 = reduce dose, G3 = interrupt treatment.',
    },
    laikDesc: {
      sk: 'Začervenanie, opuch a bolesť dlaní a chodidiel. Spôsobené niektorými liekmi v chemoterapii.',
      en: 'Redness, swelling and pain on palms and soles. Caused by certain chemo drugs.',
    },
    category: 'toxicity',
  },
  {
    abbr: 'Fatigue',
    fullName: { sk: 'Únava (onkologická)', en: 'Cancer-Related Fatigue' },
    proDesc: {
      sk: 'Multifaktoriálna: anémia, dehydratácia, nutričný deficit, psychický stres. NCCN odporúča stupňovitú intervenciu.',
      en: 'Multifactorial: anemia, dehydration, nutritional deficit, psychological stress. NCCN recommends graded intervention.',
    },
    laikDesc: {
      sk: 'Extrémna únava počas liečby, ktorá sa nezlepší odpočinkom. Jedna z najčastejších sťažností pacientov.',
      en: 'Extreme tiredness during treatment that rest does not improve. One of the most common patient complaints.',
    },
    category: 'toxicity',
  },
  {
    abbr: 'Nausea',
    fullName: { sk: 'Nauzea a vracanie', en: 'Nausea and Vomiting' },
    proDesc: {
      sk: 'Oxaliplatina: stredne emetogénna. Profylaxia: ondansetron + dexametazon. Oneskorené: metoklopramid.',
      en: 'Oxaliplatin: moderately emetogenic. Prophylaxis: ondansetron + dexamethasone. Delayed: metoclopramide.',
    },
    laikDesc: {
      sk: 'Nevoľnosť a zvracanie po chemoterapii. Lieky proti nevoľnosti sa podávajú preventívne.',
      en: 'Nausea and vomiting after chemo. Anti-nausea medications are given preventively.',
    },
    category: 'toxicity',
  },

  // ── 2nd-Line Treatment Options ──
  {
    abbr: 'FOLFIRI',
    fullName: { sk: 'FOLFIRI protokol', en: 'FOLFIRI Protocol' },
    proDesc: {
      sk: '5-FU + leucovorín + irinotekan. Štandard 2. línie po progresii na FOLFOX. Cyklus 14 dní.',
      en: '5-FU + leucovorin + irinotecan. Standard 2nd-line after FOLFOX progression. 14-day cycle.',
    },
    laikDesc: {
      sk: 'Alternatívna kombinácia liekov, keď prvá liečba prestane účinkovať.',
      en: 'Alternative drug combination when the first treatment stops working.',
    },
    category: 'treatment',
  },
  {
    abbr: 'FOLFOXIRI',
    fullName: { sk: 'FOLFOXIRI protokol', en: 'FOLFOXIRI Protocol' },
    proDesc: {
      sk: '5-FU + leucovorín + oxaliplatina + irinotekan. Intenzívnejšia trojkombinácia. ECOG 0-1. Vyššia toxicita ale lepšia RR.',
      en: '5-FU + leucovorin + oxaliplatin + irinotecan. Intensive triplet. ECOG 0-1. Higher toxicity but better RR.',
    },
    laikDesc: {
      sk: 'Najintenzívnejšia kombinácia 4 liekov. Používa sa u silnejších pacientov pre lepšiu šancu na odpoveď.',
      en: 'Most intensive combination of 4 drugs. Used in fitter patients for better chance of response.',
    },
    category: 'treatment',
  },
  {
    abbr: 'TAS-102',
    fullName: { sk: 'Trifluridín/tipiracil', en: 'Trifluridine/Tipiracil' },
    proDesc: {
      sk: 'Lonsurf. 3. línia mCRC. Perorálny fluoropyrimidín. Kombinácia s bevacizumabom (SUNLIGHT štúdia).',
      en: 'Lonsurf. 3rd-line mCRC. Oral fluoropyrimidine. Combination with bevacizumab (SUNLIGHT trial).',
    },
    laikDesc: {
      sk: 'Tablety podávané v neskorších fázach liečby, keď iné lieky prestanú účinkovať.',
      en: 'Pills given in later stages when other treatments stop working.',
    },
    category: 'treatment',
  },
  {
    abbr: 'Regorafenib',
    fullName: { sk: 'Regorafenib (Stivarga)', en: 'Regorafenib (Stivarga)' },
    proDesc: {
      sk: 'Multikinázový inhibítor. 3. línia mCRC. Perorálny, 21/28 dní. Hepatotoxicita a HFS monitorovať.',
      en: 'Multikinase inhibitor. 3rd-line mCRC. Oral, 21/28 days. Monitor hepatotoxicity and HFS.',
    },
    laikDesc: {
      sk: 'Cielený liek v tabletkovej forme pre neskoršie fázy liečby. Blokuje rast nádorových ciev.',
      en: 'Targeted drug in pill form for later-stage treatment. Blocks tumor blood vessel growth.',
    },
    category: 'treatment',
  },

  // ── Additional Biomarkers ──
  {
    abbr: 'NRAS',
    fullName: { sk: 'Neuroblastoma RAS vírusový onkogén', en: 'Neuroblastoma RAS Viral Oncogene' },
    proDesc: {
      sk: 'Mutácie NRAS vylučujú anti-EGFR (cetuximab, panitumumab). Wild-type = anti-EGFR možný (ak aj KRAS + BRAF WT).',
      en: 'NRAS mutations exclude anti-EGFR (cetuximab, panitumumab). Wild-type = anti-EGFR possible (if KRAS + BRAF also WT).',
    },
    laikDesc: {
      sk: 'Ďalší gén testovaný v nádore. Spolu s KRAS rozhoduje o vhodnosti cielenej liečby.',
      en: 'Another gene tested in the tumor. Together with KRAS, determines suitability for targeted therapy.',
    },
    category: 'diagnosis',
  },
  {
    abbr: 'BRAF V600E',
    fullName: { sk: 'BRAF V600E mutácia', en: 'BRAF V600E Mutation' },
    proDesc: {
      sk: 'BRAF V600E+ mCRC: horšia prognóza. Encorafenib + cetuximab (BEACON). Bez mutácie: štandardná liečba.',
      en: 'BRAF V600E+ mCRC: worse prognosis. Encorafenib + cetuximab (BEACON). No mutation: standard treatment.',
    },
    laikDesc: {
      sk: 'Špecifická zmena v géne BRAF. Ak je prítomná, existuje špeciálna kombinácia liekov.',
      en: 'A specific change in the BRAF gene. If present, a special drug combination is available.',
    },
    category: 'diagnosis',
  },

  // ── General / Other ──
  {
    abbr: 'BSA',
    fullName: { sk: 'Plocha povrchu tela', en: 'Body Surface Area' },
    proDesc: {
      sk: 'BSA (m²) = √(výška cm × hmotnosť kg / 3600). Dávky chemo sa počítajú v mg/m². Priemerná BSA: 1.7-1.9 m².',
      en: 'BSA (m²) = √(height cm × weight kg / 3600). Chemo doses calculated in mg/m². Average BSA: 1.7-1.9 m².',
    },
    laikDesc: {
      sk: 'Meranie veľkosti tela používané na výpočet správnej dávky chemoterapie.',
      en: 'A measurement of body size used to calculate the correct chemotherapy dose.',
    },
    category: 'general',
  },
]

// Helper to search dictionary
export function searchDictionary(query: string, entries: DictionaryEntry[] = MEDICAL_DICTIONARY): DictionaryEntry[] {
  if (!query || query.length < 1) return entries
  const q = query.toLowerCase()
  return entries.filter(
    (e) =>
      e.abbr.toLowerCase().includes(q)
      || e.fullName.en.toLowerCase().includes(q)
      || e.fullName.sk.toLowerCase().includes(q)
      || e.proDesc.en.toLowerCase().includes(q)
      || e.proDesc.sk.toLowerCase().includes(q)
      || e.laikDesc.en.toLowerCase().includes(q)
      || e.laikDesc.sk.toLowerCase().includes(q),
  )
}

// Category labels
export const CATEGORY_LABELS: Record<string, { sk: string; en: string }> = {
  lab: { sk: 'Laboratórium', en: 'Lab Values' },
  tumor_marker: { sk: 'Nádorové markery', en: 'Tumor Markers' },
  treatment: { sk: 'Liečba', en: 'Treatment' },
  diagnosis: { sk: 'Diagnostika', en: 'Diagnosis' },
  inflammation: { sk: 'Zápalové indexy', en: 'Inflammation' },
  general: { sk: 'Všeobecné', en: 'General' },
  toxicity: { sk: 'Toxicita', en: 'Toxicity' },
}
