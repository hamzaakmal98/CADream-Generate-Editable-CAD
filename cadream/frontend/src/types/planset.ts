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
