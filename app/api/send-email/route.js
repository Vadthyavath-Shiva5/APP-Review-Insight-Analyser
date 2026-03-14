import nodemailer from "nodemailer";
import { promises as fs } from "fs";
import { NextResponse } from "next/server";

import { readEmailDraftParts, resolveLatestAttachmentPaths } from "../../../lib/dashboard-data.js";

// Email: Brevo (default), Resend, or SMTP. Set EMAIL_PROVIDER=brevo + BREVO_API_KEY + EMAIL_FROM_ADDRESS on Vercel.
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

    const rawProvider = (process.env.EMAIL_PROVIDER || "brevo").trim().toLowerCase();
    const emailProvider = rawProvider === "resend" || rawProvider === "smtp" ? rawProvider : "brevo";
    const fromName = process.env.EMAIL_FROM_NAME || "GROWW Pulse Bot";
    const fromEmail =
      process.env.EMAIL_FROM_ADDRESS ||
      process.env.RESEND_FROM_EMAIL ||
      process.env.BREVO_FROM_EMAIL ||
      process.env.SMTP_USERNAME ||
      "";

    if (!fromEmail) {
      return NextResponse.json(
        {
          ok: false,
          error:
            "Sender email not set. In Vercel: set EMAIL_FROM_ADDRESS (e.g. your verified Brevo sender email).",
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
            "No email draft found. Generate the report first: use “Reprocess and Send” with a week range (backend runs the pipeline), or run the pipeline on Render. Then try Send Current again.",
        },
        { status: 400 },
      );
    }
    const bodyHtml = renderHtmlBody(body);
    const { pdfPath, csvPath, pdfName, csvName } = await resolveLatestAttachmentPaths();

    const attachments = [];
    if (pdfPath && pdfName) attachments.push({ filename: pdfName, path: pdfPath });
    if (csvPath && csvName) attachments.push({ filename: csvName, path: csvPath });

    if (emailProvider === "brevo") {
      const brevoApiKey = (process.env.BREVO_API_KEY || "").trim();
      if (!brevoApiKey) {
        return NextResponse.json(
          {
            ok: false,
            error:
              "Brevo is not configured. In Vercel Environment Variables set: EMAIL_PROVIDER=brevo, BREVO_API_KEY (your Brevo API key), and EMAIL_FROM_ADDRESS (verified sender). Then redeploy.",
          },
          { status: 400 },
        );
      }

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
        message: `Email sent to ${recipientEmail}`,
        provider: "brevo",
        providerMessageId: brevoResult?.messageId || null,
        attachments: attachments.map((a) => a.filename),
      });
    }

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
      {
        ok: false,
        error:
          "To send via Brevo, set in Vercel Environment Variables: EMAIL_PROVIDER=brevo, BREVO_API_KEY, EMAIL_FROM_ADDRESS. Then redeploy.",
      },
      { status: 400 },
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to send email";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
