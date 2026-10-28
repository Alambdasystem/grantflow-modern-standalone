export type HondaOnboardingData = {
  total_program_budget?: number;
  other_funding_needed_not_secured?: number;
  deadline_local?: string;
  deadline_timezone_caveat?: string;
  character_checks?: {section:string;characters_in_supplied_draft:number;outline_limit_under:number;exceeds_outline_limit:boolean}[];
};

export function isHondaOnboarding(app:{id:number;organization_id:number|null;grant_id:number;form_data?:{honda_2027_onboarding?:HondaOnboardingData}}) {
  return app.id===47 && app.organization_id===1 && app.grant_id===72 && !!app.form_data?.honda_2027_onboarding;
}

export function hondaBudget(request:unknown,total:unknown,remaining:unknown) {
  const amount=(n:unknown)=>typeof n==='number'&&Number.isFinite(n)&&n>=0?n:null;
  const result={request:amount(request),total:amount(total),remaining:amount(remaining)};
  return {...result,reconciled:result.request!==null&&result.total!==null&&result.remaining!==null&&Math.abs(result.request+result.remaining-result.total)<0.005};
}

export const hondaSources={
  funding:'https://csr.honda.com/funding',
  pillars:'https://www.cybergrants.com/hondacsr/Honda_and_Honda_USA_Foundation_2027_Programmatic_Pillar_Awards.pdf',
  faq:'https://www.cybergrants.com/hondacsr/Honda_and_Honda_USA_Foundation_Funding_FAQs.pdf',
  portal:'https://www.cybergrants.com/hondacsr/quiz/',
};

export const hondaFiles=[
  'Honda_and_Honda_USA_Foundation_2027_Programmatic_Pillar_Awards.pdf',
  'Grant Outline.docx',
  'WYF_ThriveForce_Honda_2027_Budget_Final_With_Notes.xlsx',
  'official-faq.pdf',
];
