import { isIP } from "node:net";

export async function POST(request: Request) {
  const backendUrl = process.env.BACKEND_URL;

  if (!backendUrl) {
    return Response.json(
      { detail: "The backend URL is not configured." },
      { status: 500 },
    );
  }

  const clientIpSource = process.env.CLIENT_IP_SOURCE ?? "local";
  const runningInEcs =
    process.env.AWS_EXECUTION_ENV?.startsWith("AWS_ECS_") ?? false;

  if (runningInEcs && clientIpSource !== "alb") {
    console.error("ECS requires CLIENT_IP_SOURCE=alb.");

    return Response.json(
      { detail: "The demo is temporarily unavailable." },
      { status: 503 },
    );
  }
  let clientIp: string;

  if (clientIpSource === "alb") {
    const forwardedFor = request.headers.get("x-forwarded-for");
    const candidate = forwardedFor?.split(",").pop()?.trim();

    if (!candidate || isIP(candidate) === 0) {
      return Response.json(
        { detail: "Unable to verify the request's client address." },
        { status: 400 },
      );
    }

    clientIp = candidate;
  } else if (clientIpSource === "local") {
    clientIp = "127.0.0.1";
  } else {
    return Response.json(
      { detail: "The client address configuration is invalid." },
      { status: 500 },
    );
  }

  let body: unknown;

  try {
    body = await request.json();
  } catch {
    return Response.json(
      { detail: "The request body must be valid JSON." },
      { status: 400 },
    );
  }

  try {
    const backendResponse = await fetch(
      `${backendUrl.replace(/\/+$/, "")}/chat`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Client-IP": clientIp,
        },
        body: JSON.stringify(body),
        cache: "no-store",
      },
    );

    const data: unknown = await backendResponse.json();

    const responseHeaders = new Headers({
      "Cache-Control": "no-store",
    });

    const retryAfter = backendResponse.headers.get("Retry-After");

    if (retryAfter !== null) {
      responseHeaders.set("Retry-After", retryAfter);
    }

    return Response.json(data, {
      status: backendResponse.status,
      headers: responseHeaders,
    });

  } catch (error) {
    console.error("Chat backend request failed:", error);

    return Response.json(
      { detail: "Unable to get a response from the backend." },
      { status: 502 },
    );
  }
}