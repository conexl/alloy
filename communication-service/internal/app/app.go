package app

import (
	"context"

	"communication-service/internal/config"
	"communication-service/internal/repository"
	"communication-service/internal/services"
	"communication-service/internal/workers"

	"github.com/sirupsen/logrus"
	"go.uber.org/fx"
)

type App struct {
	logger           *logrus.Logger
	rfqSenderWorker  *workers.RFQSenderWorker
	imapListener     *workers.IMAPListenerWorker
	aiBatchWorker    *workers.AIBatchWorker
	orphanRetryWorker *workers.OrphanRetryWorker
}

func NewApp(
	logger *logrus.Logger,
	rfqSenderWorker *workers.RFQSenderWorker,
	imapListener *workers.IMAPListenerWorker,
	aiBatchWorker *workers.AIBatchWorker,
	orphanRetryWorker *workers.OrphanRetryWorker,
) *App {
	return &App{
		logger:            logger,
		rfqSenderWorker:   rfqSenderWorker,
		imapListener:      imapListener,
		aiBatchWorker:     aiBatchWorker,
		orphanRetryWorker: orphanRetryWorker,
	}
}

func (a *App) Start(ctx context.Context) {
	a.logger.Info("Communication service started")
	// Workers are already started via fx hooks
	<-ctx.Done()
}

func (a *App) Stop() {
	a.logger.Info("Communication service stopping")
}

var Module = fx.Module("app",
	fx.Provide(
		// Config
		config.Load,

		// Logger
		func() *logrus.Logger {
			logger := logrus.New()
			logger.SetFormatter(&logrus.JSONFormatter{
				TimestampFormat: "2006-01-02 15:04:05",
			})
			logger.SetLevel(logrus.InfoLevel)
			return logger
		},

		// Repositories
		func(cfg *config.Config, logger *logrus.Logger) (*repository.PostgresRepository, error) {
			return repository.NewPostgresRepository(cfg.DBDSN, logger)
		},

		func(cfg *config.Config, logger *logrus.Logger) (*repository.RedisRepository, error) {
			return repository.NewRedisRepository(cfg.RedisURL, logger)
		},

		// Services
		func(cfg *config.Config, logger *logrus.Logger) *services.SMTPClient {
			return services.NewSMTPClient(cfg, logger)
		},

		func(logger *logrus.Logger) *services.TemplateService {
			return services.NewTemplateService(logger)
		},

		func(logger *logrus.Logger) *services.QuoteParser {
			return services.NewQuoteParser(logger)
		},

		func(cfg *config.Config, logger *logrus.Logger) *services.OpenRouterClient {
			return services.NewOpenRouterClient(cfg, logger)
		},

		func(logger *logrus.Logger) *services.AttachmentParser {
			return services.NewAttachmentParser(logger)
		},

		// Workers
		workers.NewRFQSenderWorker,
		workers.NewIMAPListenerWorker,
		workers.NewAIBatchWorker,
		workers.NewOrphanRetryWorker,

		// App
		NewApp,
	),
)
