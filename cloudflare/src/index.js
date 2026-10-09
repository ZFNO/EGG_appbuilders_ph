export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    return new Response(
      JSON.stringify({ ok: true, env: env.ENVIRONMENT, path: url.pathname }),
      { headers: { 'content-type': 'application/json' } }
    );
  }
};
