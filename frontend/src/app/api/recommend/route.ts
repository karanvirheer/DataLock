// src/app/api/recommend/route.ts
import { NextResponse } from "next/server";

const AWS_API_BASE = process.env.DEADLOCK_API_BASE_URL as string;
const AWS_API_KEY = process.env.DEADLOCK_API_KEY as string;

if (!AWS_API_BASE) throw new Error("DEADLOCK_API_BASE_URL is not set");
if (!AWS_API_KEY) throw new Error("DEADLOCK_API_KEY is not set");

if (!AWS_API_BASE) {
  throw new Error("DEADLOCK_API_BASE_URL is not set – /api/recommend will fail.");
}

// POST /api/recommend
export async function POST(request: Request) {
  try {
    const payload = await request.json();

    const upstream = await fetch(`${AWS_API_BASE}/recommend`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(AWS_API_KEY ? { "x-api-key": AWS_API_KEY } : {}),
      },
      body: JSON.stringify(payload),
    });

    const text = await upstream.text();

    let data: unknown;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text;
    }

    if (!upstream.ok) {
      console.error(
        "AWS /recommend error",
        upstream.status,
        upstream.statusText,
        text,
      );
      return NextResponse.json(
        {
          error: "Upstream /recommend error",
          status: upstream.status,
          body: data,
        },
        { status: upstream.status },
      );
    }

    return NextResponse.json(data);
  } catch (err) {
    console.error("Error in /api/recommend handler:", err);
    return NextResponse.json(
      { error: "Internal error in /api/recommend" },
      { status: 500 },
    );
  }
}

export async function GET() {
  return NextResponse.json({
    ok: true,
    message: "Send POST with hero/lane payload to get recommendations.",
  });
}
