export type PlanSetInputGate = {
  ready: boolean;
  missing_reasons: string[];
};

export type PlanSetPageRequirement = "cad_ir" | "site_plan" | "sld";
export type PlanSetPageStatus = "auto" | "fixed" | "pending";

export type PlanSetManifestPage = {
  page_number: number;
  generation_mode: "auto" | "fixed";
  status: PlanSetPageStatus;
  requirements: PlanSetPageRequirement[];
  missing_reasons?: string[];
};

export type PlanSetManifest = {
  schema_version: "planset-manifest-v1";
  summary: {
    total_pages: number;
    auto_pages: number;
    fixed_pages: number;
    pending_pages: number;
  };
  input_status: {
    cad_ir: PlanSetInputGate;
    site_plan: PlanSetInputGate;
    sld: PlanSetInputGate;
  };
  pages: PlanSetManifestPage[];
};

export type PlanSetPayloadStubItem = {
  page_number: number;
  status: PlanSetPageStatus;
  payload_schema: "auto-page-payload-v1" | "fixed-page-payload-v1" | null;
  payload: Record<string, unknown> | null;
  missing_reasons?: string[];
};

export type PlanSetPayloadStubsResponse = {
  schema_version: "planset-payload-stubs-v1";
  manifest: PlanSetManifest;
  page_payloads: PlanSetPayloadStubItem[];
};

export type EngineerSignatureImage = {
  uri: string;
  mime_type: string;
  base64: string;
};

export type RightPanelMetadata = {
  ac_system_size: string;
  inverter_model: string;
  dc_system_size: string;
  bess_model: string;
  customer_website: string;
  customer_phone: string;
  customer_contact: string;
  ahj: string;
  designer_company: string;
  designer_address: string;
  designer_website: string;
  designer_phone: string;
  designer_contact: string;
  page_notes: string;
  sheet_metadata: {
    scale: string;
    sheet_title: string;
    drawn_by: string;
    checked_by: string;
    approved_by: string;
    issue_date: string;
    sheet_number: string;
    revision: string;
  };
  title_block: {
    project_name: string;
    client_name: string;
    site_address: string;
    drawn_by: string;
    checked_by: string;
    approved_by: string;
  };
  engineer_signature_image: EngineerSignatureImage;
};
