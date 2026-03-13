import { promises as fs } from "fs";
import { NextResponse } from "next/server";

import { resolveLatestAttachmentPaths } from "../../../lib/dashboard-data.js";

export const runtime = "nodejs";

export async function GET(req) {
  try {
    const { searchParams } = new URL(req.url);
    const kind = String(searchParams.get("kind") || "").toLowerCase();

    if (kind !== "pdf" && kind !== "csv") {
      return NextResponse.json({ ok: false, error: "Query param kind must be pdf or csv." }, { status: 400 });
    }

    const attachments = await resolveLatestAttachmentPaths();
    const filePath = kind === "pdf" ? attachments.pdfPath : attachments.csvPath;
    const fileName = kind === "pdf" ? attachments.pdfName : attachments.csvName;

    if (!filePath || !fileName) {
      return NextResponse.json({ ok: false, error: `Latest ${kind.toUpperCase()} file not found.` }, { status: 404 });
    }

    const content = await fs.readFile(filePath);
    const contentType = kind === "pdf" ? "application/pdf" : "text/csv; charset=utf-8";

    return new NextResponse(content, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": `attachment; filename="${fileName}"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Failed to download attachment." },
      { status: 500 },
    );
  }
}
