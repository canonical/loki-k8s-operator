// Package frontend contains provides a frontend service for ingest limits.
// It is responsible for receiving and answering gRPC requests from distributors,
// such as exceeds limits requests, forwarding them to individual limits backends,
// gathering and aggregating their responses (where required), and returning
// the final result.
package frontend

import (
	"context"
	"fmt"

	"github.com/go-kit/log"
	"github.com/go-kit/log/level"
	"github.com/grafana/dskit/limiter"
	"github.com/grafana/dskit/ring"
	"github.com/grafana/dskit/services"
	"github.com/prometheus/client_golang/prometheus"

	limits_client "github.com/grafana/loki/v3/pkg/limits/client"
	"github.com/grafana/loki/v3/pkg/logproto"
)

const (
	RingKey  = "ingest-limits-frontend"
	RingName = "ingest-limits-frontend"
)

// Frontend is the limits-frontend service, and acts a service wrapper for
// all components needed to run the limits-frontend.
type Frontend struct {
	services.Service

	cfg    Config
	logger log.Logger

	subservices        *services.Manager
	subservicesWatcher *services.FailureWatcher

	limits IngestLimitsService

	lifecycler        *ring.Lifecycler
	lifecyclerWatcher *services.FailureWatcher
}

// New returns a new Frontend.
func New(cfg Config, ringName string, limitsRing ring.ReadRing, limits Limits, logger log.Logger, reg prometheus.Registerer) (*Frontend, error) {
	var servs []services.Service

	factory := limits_client.NewPoolFactory(cfg.ClientConfig)
	pool := limits_client.NewPool(ringName, cfg.ClientConfig.PoolConfig, limitsRing, factory, logger)
	rateLimiter := limiter.NewRateLimiter(newRateLimitsAdapter(limits), cfg.RecheckPeriod)
	limitsSrv := NewRingIngestLimitsService(limitsRing, pool, limits, rateLimiter, logger, reg)

	f := &Frontend{
		cfg:    cfg,
		logger: logger,
		limits: limitsSrv,
	}

	var err error
	f.lifecycler, err = ring.NewLifecycler(cfg.LifecyclerConfig, f, RingName, RingKey, true, logger, reg)
	if err != nil {
		return nil, fmt.Errorf("failed to create %s lifecycler: %w", RingName, err)
	}
	// Watch the lifecycler
	f.lifecyclerWatcher = services.NewFailureWatcher()
	f.lifecyclerWatcher.WatchService(f.lifecycler)

	servs = append(servs, f.lifecycler)
	servs = append(servs, pool)
	mgr, err := services.NewManager(servs...)
	if err != nil {
		return nil, err
	}

	f.subservices = mgr
	f.subservicesWatcher = services.NewFailureWatcher()
	f.subservicesWatcher.WatchManager(f.subservices)
	f.Service = services.NewBasicService(f.starting, f.running, f.stopping)

	return f, nil
}

// starting implements services.Service.
func (f *Frontend) starting(ctx context.Context) (err error) {
	defer func() {
		if err == nil {
			return
		}
		stopErr := services.StopManagerAndAwaitStopped(context.Background(), f.subservices)
		if stopErr != nil {
			level.Error(f.logger).Log("msg", "failed to stop subservices", "err", stopErr)
		}
	}()

	level.Info(f.logger).Log("msg", "starting subservices")
	if err := services.StartManagerAndAwaitHealthy(ctx, f.subservices); err != nil {
		return fmt.Errorf("failed to start subservices: %w", err)
	}

	return nil
}

// running implements services.Service.
func (f *Frontend) running(ctx context.Context) error {
	select {
	case <-ctx.Done():
		return nil
	case err := <-f.subservicesWatcher.Chan():
		return fmt.Errorf("ingest limits frontend subservice failed: %w", err)
	}
}

// stopping implements services.Service.
func (f *Frontend) stopping(_ error) error {
	return services.StopManagerAndAwaitStopped(context.Background(), f.subservices)
}

// ExceedsLimits implements logproto.IngestLimitsFrontendClient.
func (f *Frontend) ExceedsLimits(ctx context.Context, r *logproto.ExceedsLimitsRequest) (*logproto.ExceedsLimitsResponse, error) {
	return f.limits.ExceedsLimits(ctx, r)
}

func (f *Frontend) CheckReady(ctx context.Context) error {
	if f.State() != services.Running && f.State() != services.Stopping {
		return fmt.Errorf("ingest limits frontend not ready: %v", f.State())
	}

	err := f.lifecycler.CheckReady(ctx)
	if err != nil {
		level.Error(f.logger).Log("msg", "ingest limits frontend not ready", "err", err)
		return err
	}

	return nil
}

// Flush implements ring.FlushTransferer. It transfers state to another ingest
// limits frontend instance.
func (f *Frontend) Flush() {}

// TransferOut implements ring.FlushTransferer. It transfers state to another
// ingest limits frontend instance.
func (f *Frontend) TransferOut(_ context.Context) error {
	return nil
}
