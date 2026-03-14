import { promises as fs } from "fs";
import { NextResponse } from "next/server";

import { readEmailDraftParts, resolveLatestAttachmentPaths } from "../../../lib/dashboard-data.js";

// Brevo only. Set BREVO_API_KEY and EMAIL_FROM_ADDRESS on Vercel.
export const runtime = "nodejs";

function validEmail(email) {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email || "");
}

function renderHtmlBody(body) {
  const converted = body
    .split(/\r?\n/)
    .map((line) => (line ? line.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>") : "&nbsp;"))
    .join("<br/>");
  return `<div style="font-family:Segoe UI,Arial,sans-serif;line-height:1.6;color:#1f2a28;">${converted}</div>`;
}

async function sendViaBrevo({ apiKey, fromName, fromEmail, toEmail, subject, bodyText, bodyHtml, attachments }) {
  const brevoAttachments = await Promise.all(
    attachments.map(async (item) => {
      const bytes = await fs.readFile(item.path);
      return { name: item.filename, content: Buffer.from(bytes).toString("base64") };
    })
  );

  const response = await fetch("https://api.brevo.com/v3/smtp/email", {
    method: "POST",
    headers: {
      "api-key": apiKey,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      sender: { name: fromName, email: fromEmail },
      to: [{ email: toEmail }],
      subject,
      htmlContent: bodyHtml,
      textContent: bodyText,
      attachment: brevoAttachments,
    }),
    cache: "no-store",
  });

  const raw = await response.text();
  let parsed = {};
  try {
    parsed = raw ? JSON.parse(raw) : {};
  } catch {
    parsed = { raw };
  }

  if (!response.ok) {
    throw new Error(`Brevo send failed (${response.status}): ${JSON.stringify(parsed)}`);
  }

  return parsed;
}

export async function POST(req) {
  try {
    const payload = await req.json();
    const recipientEmail = String(payload?.recipientEmail || "").trim();

    if (!validEmail(recipientEmail)) {
      return NextResponse.json({ ok: false, error: "Valid recipient email is required." }, { status: 400 });
    }

    const fromName = (process.env.EMAIL_FROM_NAME || "GROWW Pulse Bot").trim();
    const fromEmail = (
      process.env.EMAIL_FROM_ADDRESS ||
      process.env.BREVO_FROM_EMAIL ||
      ""
    ).trim();
    const brevoApiKey = (process.env.BREVO_API_KEY || "").trim();

    if (!fromEmail) {
      return NextResponse.json(
        {
          ok: false,
          error: "Set EMAIL_FROM_ADDRESS in Vercel (your verified Brevo sender email).",
        },
        { status: 400 },
      );
    }

    if (!brevoApiKey) {
      return NextResponse.json(
        {
          ok: false,
          error: "Set BREVO_API_KEY in Vercel Environment Variables, then redeploy.",
        },
        { status: 400 },
      );
    }

    const { subject, body } = await readEmailDraftParts();
    if (!body || body.includes("No draft found. Please run pipeline first.")) {
      return NextResponse.json(
        {
          ok: false,
          error:
            "No email draft found. Generate the report first: use “Reprocess and Send” with a week range, or run the pipeline on Render. Then try Send Current again.",
        },
        { status: 400 },
      );
    }
    const bodyHtml = renderHtmlBody(body);
    const { pdfPath, csvPath, pdfName, csvName } = await resolveLatestAttachmentPaths();

    const attachments = [];
    if (pdfPath && pdfName) attachments.push({ filename: pdfName, path: pdfPath });
    if (csvPath && csvName) attachments.push({ filename: csvName, path: csvPath });

    const brevoResult = await sendViaBrevo({
      apiKey: brevoApiKey,
      fromName,
      fromEmail,
      toEmail: recipientEmail,
      subject,
      bodyText: body,
      bodyHtml,
      attachments,
    });

    return NextResponse.json({
      ok: true,
      message: `Email sent to ${recipientEmail} via Brevo.`,
      provider: "brevo",
      providerMessageId: brevoResult?.messageId || null,
      attachments: attachments.map((a) => a.filename),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to send email";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
