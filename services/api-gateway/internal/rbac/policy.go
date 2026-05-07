package rbac

import (
	"net/http"
	"slices"
	"strings"

	"github.com/qumulo/gpu-horizon/api-gateway/internal/auth"
)

// Role names map onto GPU Horizon RBAC roles as defined in the architecture.
const (
	RoleAdmin    = "gpu-horizon:admin"
	RoleOperator = "gpu-horizon:operator"
	RoleViewer   = "gpu-horizon:viewer"
)

// actionRoles maps HTTP method+path-prefix pairs to the minimum required role.
// Evaluation is first-match; more specific prefixes should come first.
var actionRoles = []struct {
	method string
	prefix string
	role   string
}{
	// Deployments: operator or admin required
	{"POST", "/api/v1/deployments", RoleOperator},
	{"DELETE", "/api/v1/deployments", RoleOperator},
	{"POST", "/api/v1/configure", RoleOperator},
	// All other reads: viewer or above
	{"GET", "/", RoleViewer},
	{"POST", "/", RoleViewer},
}

func hasRole(groups []string, required string) bool {
	// Admin satisfies any role check.
	if slices.Contains(groups, RoleAdmin) {
		return true
	}
	if required == RoleOperator {
		return slices.Contains(groups, RoleOperator)
	}
	// Viewer: everyone with any GPU Horizon role.
	for _, g := range groups {
		if strings.HasPrefix(g, "gpu-horizon:") {
			return true
		}
	}
	return false
}

// Middleware enforces role-based access on top of authenticated claims.
func Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		claims := auth.FromContext(r.Context())
		if claims == nil {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}

		required := requiredRole(r.Method, r.URL.Path)
		if !hasRole(claims.Groups, required) {
			http.Error(w, "Forbidden", http.StatusForbidden)
			return
		}

		next.ServeHTTP(w, r)
	})
}

func requiredRole(method, path string) string {
	for _, rule := range actionRoles {
		if rule.method == method && strings.HasPrefix(path, rule.prefix) {
			return rule.role
		}
	}
	return RoleViewer
}
