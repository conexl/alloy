package main

import (
	"context"
	"os"
	"os/signal"
	"syscall"

	"communication-service/internal/app"

	"go.uber.org/fx"
)

func main() {
	fxApp := fx.New(
		app.Module,
		fx.Invoke(func(lc fx.Lifecycle, app *app.App) {
			lc.Append(fx.Hook{
				OnStart: func(ctx context.Context) error {
					go app.Start(ctx)
					return nil
				},
				OnStop: func(ctx context.Context) error {
					app.Stop()
					return nil
				},
			})
		}),
	)

	if err := fxApp.Start(context.Background()); err != nil {
		panic(err)
	}

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	<-sigChan

	fxApp.Stop(context.Background())
}