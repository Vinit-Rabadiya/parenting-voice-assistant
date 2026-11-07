// General explanations; routine programme ages live in vaccineSchedule.js.
export const checkedOn = "2026-11-06";
export const reviewDays = 90;

const who = {
  title: "WHO: What is vaccination?",
  url: "https://www.who.int/news-room/questions-and-answers/item/vaccines-and-immunization-what-is-vaccination",
};
const diseases = {
  title: "UNICEF: Vaccines and the diseases they prevent",
  url: "https://www.unicef.org/parenting/health/vaccines-and-diseases-they-prevent",
};
const questions = {
  title: "UNICEF: Vaccines for children — your questions answered",
  url: "https://www.unicef.org/parenting/health/parents-frequently-asked-questions-vaccines",
};

export const entries = [
  {
    id: "how", category: "Common questions", title: "How do vaccines work?",
    keywords: "immunity protection antibodies why vaccinate",
    text: "Vaccines help the immune system recognise particular infections and prepare to fight them. They help protect children before they encounter those diseases.",
    sources: [who], question: "How do vaccines help protect my baby?",
  },
  {
    id: "bcg", category: "Vaccine names", title: "BCG",
    keywords: "tuberculosis tb booklet abbreviation",
    text: "BCG is a vaccine against tuberculosis (TB), an infection that can affect the lungs and other organs.",
    sources: [diseases], question: "What does the BCG vaccine protect against?",
  },
  {
    id: "polio", category: "Vaccine names", title: "OPV and IPV — polio",
    keywords: "oral inactivated drops injection booklet abbreviation",
    text: "Both are polio vaccines. OPV means oral polio vaccine; IPV means inactivated polio vaccine. Polio can cause paralysis.",
    sources: [{
      title: "WHO: Poliomyelitis — questions and answers",
      url: "https://www.who.int/news-room/questions-and-answers/item/poliomyelitis",
    }], question: "What is the difference between OPV and IPV vaccines?",
  },
  {
    id: "pentavalent", category: "Vaccine names", title: "Pentavalent — five-in-one",
    keywords: "penta dtp dpt diphtheria tetanus pertussis whooping cough hepatitis b hib haemophilus",
    text: "Pentavalent combines protection against diphtheria, tetanus, whooping cough, hepatitis B and Haemophilus influenzae type b (Hib).",
    sources: [{
      title: "WHO: Tetanus and combination vaccines",
      url: "https://www.who.int/teams/immunization-vaccines-and-biologicals/diseases/tetanus/1000",
    }], question: "What does the pentavalent vaccine protect against?",
  },
  {
    id: "pcv", category: "Vaccine names", title: "PCV — pneumococcal",
    keywords: "pneumonia meningitis pcv10 pcv13 booklet abbreviation",
    text: "PCV means pneumococcal conjugate vaccine. It helps protect against pneumococcal infections, which can cause pneumonia, meningitis and other illnesses.",
    sources: [diseases], question: "What does PCV mean in my baby's vaccination booklet?",
  },
  {
    id: "rotavirus", category: "Vaccine names", title: "Rotavirus",
    keywords: "rotarix rotavac diarrhoea diarrhea vomiting oral",
    text: "Rotavirus vaccines help protect against rotavirus, which can cause severe diarrhoea, vomiting and dehydration in young children.",
    note: "Ask the clinic to explain the vaccine product recorded in your booklet.",
    sources: [diseases], question: "What does the rotavirus vaccine protect against?",
  },
  {
    id: "mr", category: "Vaccine names", title: "MR — measles and rubella",
    keywords: "measles rubella booklet abbreviation",
    text: "MR combines protection against measles and rubella. Measles can cause serious complications. Rubella can harm an unborn baby if contracted during pregnancy.",
    note: "MR and MMR are different combinations; MMR also includes mumps. Ask the clinic to clarify unfamiliar entries.",
    sources: [diseases, {
      title: "Kenya Ministry of Health: Measles-rubella and typhoid vaccination",
      url: "https://www.health.go.ke/node/1955",
    }], question: "What does MR mean in my baby's vaccination booklet?",
  },
  {
    id: "tcv", category: "Vaccine names", title: "TCV — typhoid",
    keywords: "conjugate typhi booklet abbreviation",
    text: "TCV means typhoid conjugate vaccine. It helps protect against typhoid fever, a bacterial infection usually spread through contaminated food or water.",
    sources: [{ title: "WHO: Typhoid", url: "https://www.who.int/news-room/fact-sheets/detail/typhoid" }],
    question: "What does the TCV vaccine protect against?",
  },
  {
    id: "malaria", category: "Vaccine names", title: "Malaria — RTS,S and R21",
    keywords: "mosquito regional eligibility",
    text: "RTS,S and R21 help protect children against Plasmodium falciparum malaria. Vaccination is one part of malaria prevention, alongside other recommended measures such as insecticide-treated nets.",
    note: "The clinic confirms local programme eligibility and which product is used.",
    sources: [{ title: "WHO: Malaria vaccines — questions and answers", url: "https://www.who.int/news-room/questions-and-answers/item/q-a-on-rts-s-malaria-vaccine" }],
    question: "What do malaria vaccines protect against?",
  },
  {
    id: "yellow-fever", category: "Vaccine names", title: "Yellow fever",
    keywords: "mosquito regional eligibility",
    text: "This vaccine helps protect against yellow fever, a viral infection spread by infected mosquitoes.",
    note: "The clinic confirms whether vaccination is appropriate for your baby's age and circumstances.",
    sources: [{ title: "WHO: Yellow fever", url: "https://www.who.int/news-room/fact-sheets/detail/yellow-fever" }],
    question: "What does the yellow fever vaccine protect against?",
  },
  {
    id: "several", category: "Common questions", title: "Why several vaccines at one visit?",
    keywords: "multiple combination overload immunity together",
    text: "Recommended vaccines can be given together. Combination vaccines reduce injections, and receiving several vaccines does not overwhelm the immune system. Ask the clinic about your baby's circumstances.",
    sources: [who], question: "Why are several vaccines offered at the same visit?",
  },
  {
    id: "autism", category: "Common questions", title: "Do vaccines cause autism?",
    keywords: "rumour rumor myth family claim evidence",
    text: "Research has found no link between vaccines and autism. If a claim worries you, discuss it with a healthcare worker and check the original evidence.",
    sources: [questions], question: "What evidence addresses the claim that vaccines cause autism?",
  },
  {
    id: "missed", category: "Common questions", title: "What if an entry is missing or unclear?",
    keywords: "booklet record missed overdue catch up appointment",
    text: "An empty space does not establish whether a vaccine was given. Take the booklet to your clinic to check the record and discuss any missed vaccinations.",
    note: "LittleCare cannot infer previous doses or calculate a personal catch-up plan.",
    sources: [who], question: "My baby's vaccination booklet has an unclear entry. What should I ask the clinic to check?",
  },
  {
    id: "effects", category: "Common questions", title: "Can vaccines have side effects?",
    keywords: "soreness mild fever safety risk concern",
    text: "Some vaccines can cause temporary soreness or mild fever; serious side effects are rare. This general information cannot tell whether a particular symptom is harmless or caused by vaccination. Contact a health professional if you are concerned about your baby.",
    sources: [questions], question: "What general side effects can vaccines have?",
  },
];

export function sourceCheckIsCurrent(date, now = new Date()) {
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  const elapsed = (today - Date.parse(`${date}T00:00:00Z`)) / 86400000;
  return Number.isFinite(elapsed) && elapsed >= 0 && elapsed <= reviewDays;
}

export function educationIsCurrent(now = new Date()) {
  return sourceCheckIsCurrent(checkedOn, now);
}
