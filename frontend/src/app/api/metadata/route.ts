// src/app/api/heroes/route.ts
import { NextResponse } from "next/server";

const API_BASE_URL = process.env.DEADLOCK_API_BASE_URL as string;
const API_KEY = process.env.DEADLOCK_API_KEY as string;

if (!API_BASE_URL) throw new Error("DEADLOCK_API_BASE_URL is not set");
if (!API_KEY) throw new Error("DEADLOCK_API_KEY is not set");

export async function GET() {
  try {
    const res = await fetch(`${API_BASE_URL}/metadata`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
      },
    });

    const text = await res.text();
    const json = text ? JSON.parse(text) : null;

    return NextResponse.json(json, { status: res.status });
  } catch (err) {
    console.error("Error in /api/heroes:", err);
    return NextResponse.json(
      { error: "Failed to fetch heroes" },
      { status: 500 },
    );
  }
}
