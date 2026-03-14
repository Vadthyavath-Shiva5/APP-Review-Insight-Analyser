import nodemailer from "nodemailer";
import { promises as fs } from "fs";
import { NextResponse } from "next/server";

import { readEmailDraftParts, resolveLatestAttachmentPaths } from "../../../lib/dashboard-data.js";

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

async function buildResendAttachments(attachments) {
  const prepared = [];
  for (const item of attachments) {
    const bytes = await fs.readFile(item.path);
    prepared.push({
      filename: item.filename,
      content: Buffer.from(bytes).toString("base64"),
    });
  }
  return prepared;
}

async function sendViaResend({ apiKey, fromName, fromEmail, toEmail, subject, bodyText, bodyHtml, attachments }) {
  const resendAttachments = await buildResendAttachments(attachments);

  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: `${fromName} <${fromEmail}>`,
      to: [toEmail],
      subject,
      text: bodyText,
      html: bodyHtml,
      attachments: resendAttachments,
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
    throw new Error(`Resend send failed (${response.status}): ${JSON.stringify(parsed)}`);
  }

  return parsed;
}

async function sendViaSmtp({
  host,
  port,
  username,
  password,
  fromName,
  fromEmail,
  toEmail,
  subject,
  bodyText,
  bodyHtml,
  attachments,
}) {
  const transporter = nodemailer.createTransport({
    host,
    port,
    secure: false,
    auth: {
      user: username,
      pass: password,
    },
  });

  await transporter.sendMail({
    from: `${fromName} <${fromEmail}>`,
    to: toEmail,
    subject,
    text: bodyText,
    html: bodyHtml,
    attachments,
  });
}

export async function POST(req) {
  try {
    const payload = await req.json();
    const recipientEmail = String(payload?.recipientEmail || "").trim();

    if (!validEmail(recipientEmail)) {
      return NextResponse.json({ ok: false, error: "Valid recipient email is required." }, { status: 400 });
    }

    const emailProvider = String(process.env.EMAIL_PROVIDER || "resend").toLowerCase();
    const fromName = process.env.EMAIL_FROM_NAME || "GROWW Pulse Bot";
    const fromEmail = process.env.EMAIL_FROM_ADDRESS || process.env.RESEND_FROM_EMAIL || process.env.SMTP_USERNAME || "";

    if (!fromEmail) {
      return NextResponse.json(
        { ok: false, error: "Set EMAIL_FROM_ADDRESS or RESEND_FROM_EMAIL or SMTP_USERNAME." },
        { status: 400 },
      );
    }

    const { subject, body } = await readEmailDraftParts();
    const bodyHtml = renderHtmlBody(body);
    const { pdfPath, csvPath, pdfName, csvName } = await resolveLatestAttachmentPaths();

    const attachments = [];
    if (pdfPath && pdfName) attachments.push({ filename: pdfName, path: pdfPath });
    if (csvPath && csvName) attachments.push({ filename: csvName, path: csvPath });

    if (emailProvider === "resend") {
      const resendApiKey = process.env.RESEND_API_KEY || "";
      if (!resendApiKey) {
        return NextResponse.json({ ok: false, error: "RESEND_API_KEY must be configured." }, { status: 400 });
      }

      const resendResult = await sendViaResend({
        apiKey: resendApiKey,
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
        message: `Email sent to ${recipientEmail}`,
        provider: "resend",
        providerMessageId: resendResult?.id || null,
        attachments: attachments.map((a) => a.filename),
      });
    }

    if (emailProvider === "smtp") {
      const smtpHost = process.env.SMTP_HOST || "smtp.gmail.com";
      const smtpPort = Number(process.env.SMTP_PORT || 587);
      const smtpUser = process.env.SMTP_USERNAME || "";
      const smtpPass = process.env.SMTP_PASSWORD || "";

      if (!smtpUser || !smtpPass) {
        return NextResponse.json(
          { ok: false, error: "SMTP_USERNAME and SMTP_PASSWORD must be configured for SMTP mode." },
          { status: 400 },
        );
      }

      await sendViaSmtp({
        host: smtpHost,
        port: smtpPort,
        username: smtpUser,
        password: smtpPass,
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
        message: `Email sent to ${recipientEmail}`,
        provider: "smtp",
        attachments: attachments.map((a) => a.filename),
      });
    }

    return NextResponse.json(
      { ok: false, error: "EMAIL_PROVIDER must be either 'resend' or 'smtp'." },
      { status: 400 },
    );
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Failed to send email" },
      { status: 500 },
    );
  }
}
