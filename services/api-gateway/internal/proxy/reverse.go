package proxy

import (
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
)

// upstreamEnv maps URL path prefixes to environment variable names
// that hold the upstream service base URL.
var upstreamEnv = map[string]string{
	"/api/v1/regions":     "GPU_CHASE_MONITOR_URL",
	"/api/v1/skus":        "GPU_CHASE_MONITOR_URL",
	"/api/v1/configure":   "GPU_CHASE_MONITOR_URL",
	"/api/v1/deployments": "PROVISIONING_ENGINE_URL",
	"/api/v1/cost":        "COST_TELEMETRY_URL",
}

func defaultURL(envKey, fallback string) string {
	if v := os.Getenv(envKey); v != "" {
		return v
	}
	return fallback
}

var upstreamDefaults = map[string]string{
	"GPU_CHASE_MONITOR_URL":  "http://gpu-chase-monitor:8001",
	"PROVISIONING_ENGINE_URL": "http://provisioning-engine:8002",
	"COST_TELEMETRY_URL":     "http://cost-telemetry:8003",
}

// Handler returns a mux that reverse-proxies requests to the appropriate backend.
func Handler() http.Handler {
	mux := http.NewServeMux()

	// Build one reverse proxy per unique upstream URL, then register every prefix.
	proxies := map[string]*httputil.ReverseProxy{}
	for _, envKey := range upstreamEnv {
		if proxies[envKey] != nil {
			continue
		}
		target := defaultURL(envKey, upstreamDefaults[envKey])
		u, err := url.Parse(target)
		if err != nil {
			panic("invalid upstream URL for " + envKey + ": " + err.Error())
		}
		proxies[envKey] = httputil.NewSingleHostReverseProxy(u)
	}

	for prefix, envKey := range upstreamEnv {
		rp := proxies[envKey]
		mux.Handle(prefix+"/", rp)
		mux.Handle(prefix, rp)
	}

	return mux
}
