package auth

import (
	"context"
	"errors"
	"net/http"
	"os"
	"strings"

	"github.com/coreos/go-oidc/v3/oidc"
)

// Claims are the validated JWT claims attached to a request context.
type Claims struct {
	Subject string
	Email   string
	Groups  []string
}

type contextKey string

const claimsKey contextKey = "claims"

// Middleware validates a Bearer token using OIDC discovery.
// When OIDC_ISSUER is not set (e.g. local dev), the middleware passes through
// with a synthetic admin identity so development does not require a real IdP.
func Middleware(next http.Handler) http.Handler {
	issuer := os.Getenv("OIDC_ISSUER")
	clientID := os.Getenv("OIDC_CLIENT_ID")

	if issuer == "" {
		return devPassthrough(next)
	}

	provider, err := oidc.NewProvider(context.Background(), issuer)
	if err != nil {
		panic("OIDC provider init failed: " + err.Error())
	}

	verifier := provider.Verifier(&oidc.Config{ClientID: clientID})

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token, err := extractBearer(r)
		if err != nil {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}

		idToken, err := verifier.Verify(r.Context(), token)
		if err != nil {
			http.Error(w, "Invalid token", http.StatusUnauthorized)
			return
		}

		var raw struct {
			Email  string   `json:"email"`
			Groups []string `json:"groups"`
		}
		_ = idToken.Claims(&raw)

		ctx := context.WithValue(r.Context(), claimsKey, &Claims{
			Subject: idToken.Subject,
			Email:   raw.Email,
			Groups:  raw.Groups,
		})
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func devPassthrough(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ctx := context.WithValue(r.Context(), claimsKey, &Claims{
			Subject: "dev-user",
			Email:   "dev@qumulo.internal",
			Groups:  []string{"gpu-horizon:admin"},
		})
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func extractBearer(r *http.Request) (string, error) {
	h := r.Header.Get("Authorization")
	if !strings.HasPrefix(h, "Bearer ") {
		return "", errors.New("missing bearer token")
	}
	return strings.TrimPrefix(h, "Bearer "), nil
}

// FromContext retrieves claims from the request context.
func FromContext(ctx context.Context) *Claims {
	c, _ := ctx.Value(claimsKey).(*Claims)
	return c
}
