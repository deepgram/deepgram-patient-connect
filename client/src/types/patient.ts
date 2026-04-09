export interface PatientRecord {
  record_id: string
  patient: {
    first_name: string
    last_name: string
    date_of_birth: string
    phone: string
    state: string
    state_full: string
    preferred_language: string
    insurance: { type: string; is_government_plan: boolean }
  }
  clinical: {
    primary_condition: string
    icd10_code: string
    current_medication: string
    prescriber: string
    pharmacy: string
  }
  promotion: {
    drug_name: string
    manufacturer: string
    promotion_type: string
    benefit_description: string
    max_annual_benefit_usd: number
    eligibility_criteria: string
    patient_is_eligible: boolean
    ineligibility_reason: string | null
  }
  call: {
    scheduled_datetime: string
    attempt_number: number
    scenario_type: string
    scenario_label: string
    expected_outcome: string
    agent_notes: string
    is_edge_case: boolean
  }
}

export type DataView = 'patients' | 'promotions' | 'scenarios'

export interface PromotionRow {
  drug_name: string
  manufacturer: string
  promotion_type: string
  eligible_patients: number
}

export interface ScenarioRow {
  scenario_type: string
  scenario_label: string
  count: number
}
