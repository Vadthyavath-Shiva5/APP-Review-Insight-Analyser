import nodemailer from "nodemailer";
import { NextResponse } from "next/server";

import { readEmailDraftParts, resolveLatestAttachmentPaths } from "../../../lib/dashboard-data.js";

export const runtime = "nodejs";

function validEmail(email) {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email || "");
}

export async function POST(req) {
  try {
    const payload = await req.json();
    const recipientEmail = String(payload?.recipientEmail || "").trim();

    if (!validEmail(recipientEmail)) {
      return NextResponse.json({ ok: false, error: "Valid recipient email is required." }, { status: 400 });
    }

    const smtpHost = process.env.SMTP_HOST || "smtp.gmail.com";
    const smtpPort = Number(process.env.SMTP_PORT || 587);
    const smtpUser = process.env.SMTP_USERNAME || "";
    const smtpPass = process.env.SMTP_PASSWORD || "";
    const smtpTls = String(process.env.SMTP_USE_TLS || "true").toLowerCase() !== "false";
    const fromName = process.env.EMAIL_FROM_NAME || "GROWW Pulse Bot";

    if (!smtpUser || !smtpPass) {
      return NextResponse.json(
        { ok: false, error: "SMTP_USERNAME and SMTP_PASSWORD must be configured." },
        { status: 400 },
      );
    }

    const { subject, body } = await readEmailDraftParts();
    const { pdfPath, csvPath, pdfName, csvName } = await resolveLatestAttachmentPaths();

    const attachments = [];
    if (pdfPath && pdfName) attachments.push({ filename: pdfName, path: pdfPath });
    if (csvPath && csvName) attachments.push({ filename: csvName, path: csvPath });

    const transporter = nodemailer.createTransport({
      host: smtpHost,
      port: smtpPort,
      secure: false,
      auth: {
        user: smtpUser,
        pass: smtpPass,
      },
    });

    const htmlBody = body
      .split(/\r?\n/)
      .map((line) => (line ? line.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>") : "&nbsp;"))
      .join("<br/>");

    await transporter.sendMail({
      from: `${fromName} <${smtpUser}>`,
      to: recipientEmail,
      subject,
      text: body,
      html: `<div style="font-family:Segoe UI,Arial,sans-serif;line-height:1.6;color:#1f2a28;">${htmlBody}</div>`,
      attachments,
    });

    return NextResponse.json({
      ok: true,
      message: `Email sent to ${recipientEmail}`,
      attachments: attachments.map((a) => a.filename),
    });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Failed to send email" },
      { status: 500 },
    );
  }
}
