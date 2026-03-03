type ExportRequestPayload = {
  total_pages: number;
  cad_ir: unknown;
  site_placements: unknown;
  sld_session: unknown;
  source_token?: string;
  source_file_name?: string;
  right_panel_metadata?: unknown;
};

async function resolveErrorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const err = (await response.json()) as { detail?: string };
    if (typeof err.detail === "string" && err.detail.trim()) {
      return err.detail;
    }
  } catch {
    // Keep fallback detail when response is not JSON.
  }
  return fallback;
}

async function postBinary(
  url: string,
  payload: ExportRequestPayload,
  fallbackErrorMessage: string,
): Promise<Response> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await resolveErrorDetail(response, fallbackErrorMessage));
  }

  return response;
}

export async function exportAutoPagesZip(payload: ExportRequestPayload): Promise<Blob> {
  const response = await postBinary(
    "/api/planset/auto-pages/export",
    payload,
    "Failed to export auto pages DXF zip.",
  );
  return response.blob();
}

export async function exportPreservedPlansetDxf(payload: ExportRequestPayload): Promise<Blob> {
  const response = await postBinary(
    "/api/planset/preserved-dxf/export",
    payload,
    "Failed to export preserved detailed DXF.",
  );
  return response.blob();
}

export async function exportPlansetPdfResponse(payload: ExportRequestPayload): Promise<Response> {
  return postBinary(
    "/api/planset/pages/pdf-export",
    payload,
    "Failed to generate pages PDF.",
  );
}

export async function generatePagesFromDxfZip(args: {
  file: File;
  viewSpecMode?: "manifest14" | "heuristic" | "provided";
  providedViewSpecs?: unknown;
  templateId?: string;
}): Promise<Blob> {
  const formData = new FormData();
  formData.append("file", args.file);
  formData.append("view_spec_mode", args.viewSpecMode ?? "manifest14");
  formData.append("template_id", args.templateId ?? "template-v1");

  if (typeof args.providedViewSpecs !== "undefined") {
    formData.append("provided_view_specs", JSON.stringify(args.providedViewSpecs));
  }

  const response = await fetch("/api/planset/generate-from-dxf", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await resolveErrorDetail(response, "Failed to generate pages from DXF."));
  }

  return response.blob();
}
