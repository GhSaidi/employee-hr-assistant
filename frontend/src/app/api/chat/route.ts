export async function POST(request: Request) {
  const backendUrl = process.env.BACKEND_URL;

  if (!backendUrl) {
    return Response.json(
      { detail: "The backend URL is not configured." },
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
        },
        body: JSON.stringify(body),
        cache: "no-store",
      },
    );

    const data: unknown = await backendResponse.json();

    return Response.json(data, {
      status: backendResponse.status,
    });
  } catch (error) {
    console.error("Chat backend request failed:", error);

    return Response.json(
      { detail: "Unable to get a response from the backend." },
      { status: 502 },
    );
  }
}