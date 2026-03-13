import { NextResponse } from "next/server";

export const runtime = "nodejs";

const MIN_REPROCESS_WEEKS = 6;

function validEmail(email) {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email || "");
}

function validWeekRange(weeksFrom, weeksTo) {
  const wf = Number(weeksFrom);
  const wt = Number(weeksTo);
  if (!Number.isInteger(wf) || !Number.isInteger(wt)) return false;
  if (wf < 1 || wf > 15 || wt < 1 || wt > 15) return false;
  if (wf > wt) return false;
  return wt - wf + 1 >= MIN_REPROCESS_WEEKS;
}

export async function POST(req) {
  try {
    const payload = await req.json();
    const recipientEmail = String(payload?.recipientEmail || "").trim();
    const weeksFrom = Number(payload?.weeksFrom);
    const weeksTo = Number(payload?.weeksTo);

    if (!validEmail(recipientEmail)) {
      return NextResponse.json({ ok: false, error: "Valid recipient email is required." }, { status: 400 });
    }
    if (!validWeekRange(weeksFrom, weeksTo)) {
      return NextResponse.json(
        {
          ok: false,
          error: `Week range must be between 1 and 15, with From <= To, and span at least ${MIN_REPROCESS_WEEKS} weeks.`,
        },
        { status: 400 },
      );
    }

    const triggerUrl = process.env.PIPELINE_TRIGGER_URL || "";
    const triggerToken = process.env.PIPELINE_TRIGGER_TOKEN || "";

    if (!triggerUrl) {
      return NextResponse.json(
        {
          ok: false,
          error:
            "PIPELINE_TRIGGER_URL is not configured. On Vercel, use an external backend job endpoint to reprocess and send.",
        },
        { status: 501 },
      );
    }

    const response = await fetch(triggerUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(triggerToken ? { Authorization: `Bearer ${triggerToken}` } : {}),
      },
      body: JSON.stringify({
        appId: "com.nextbillion.groww",
        recipientEmail,
        weeksFrom,
        weeksTo,
        deliveryMode: "instant_frontend",
      }),
      cache: "no-store",
    });

    const resultText = await response.text();
    let resultJson = null;
    try {
      resultJson = JSON.parse(resultText);
    } catch {
      resultJson = { raw: resultText };
    }

    if (!response.ok) {
      return NextResponse.json(
        {
          ok: false,
          error: "Backend reprocess call failed.",
          details: resultJson,
        },
        { status: 502 },
      );
    }

    return NextResponse.json({ ok: true, message: "Reprocess and send triggered.", details: resultJson });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "Failed to trigger reprocess" },
      { status: 500 },
    );
  }
}
