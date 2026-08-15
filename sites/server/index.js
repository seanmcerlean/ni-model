function indexRequest(request) {
  const url = new URL(request.url);
  url.pathname = "/index.html";
  return new Request(url, request);
}

export default {
  async fetch(request, environment) {
    const response = await environment.ASSETS.fetch(request);
    if (response.status !== 404 || request.method !== "GET") {
      return response;
    }
    return environment.ASSETS.fetch(indexRequest(request));
  },
};
