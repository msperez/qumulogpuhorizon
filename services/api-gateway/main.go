package main

import (
	"log"
	"net/http"
	"os"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"

	"github.com/qumulo/gpu-horizon/api-gateway/internal/auth"
	"github.com/qumulo/gpu-horizon/api-gateway/internal/proxy"
	"github.com/qumulo/gpu-horizon/api-gateway/internal/rbac"
)

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}

	r := chi.NewRouter()

	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.Timeout(60 * time.Second))
	r.Use(cors.Handler(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowedMethods:   []string{"GET", "POST", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Authorization", "Content-Type", "X-Request-Id"},
		AllowCredentials: false,
	}))

	// Health check — unauthenticated
	r.Get("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"status":"ok"}`))
	})

	// All /api routes require OIDC auth + RBAC
	r.Group(func(r chi.Router) {
		r.Use(auth.Middleware)
		r.Use(rbac.Middleware)
		r.Mount("/api", proxy.Handler())
	})

	log.Printf("GPU Horizon API Gateway listening on :%s", port)
	if err := http.ListenAndServe(":"+port, r); err != nil {
		log.Fatal(err)
	}
}
