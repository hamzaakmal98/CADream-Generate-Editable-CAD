type ExportRequestPayload = {
  total_pages: number;
  cad_ir: unknown;
  site_placements: unknown;
  sld_session: unknown;
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

export async function exportPlansetPdfResponse(payload: ExportRequestPayload): Promise<Response> {
  return postBinary(
    "/api/planset/pages/pdf-export",
    payload,
    "Failed to generate pages PDF.",
  );
}
