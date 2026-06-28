-- CreateTable
CREATE TABLE "draws" (
    "id" SERIAL NOT NULL,
    "date" DATE NOT NULL,
    "back3" VARCHAR(3) NOT NULL,
    "last2" VARCHAR(2),
    "first_prize" VARCHAR(6),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "draws_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "model_versions" (
    "id" SERIAL NOT NULL,
    "trained_at" TIMESTAMP(3) NOT NULL,
    "n_draws" INTEGER NOT NULL,
    "weight_lr" DOUBLE PRECISION NOT NULL,
    "weight_rf" DOUBLE PRECISION NOT NULL,
    "weight_gb" DOUBLE PRECISION NOT NULL,
    "metrics" JSONB NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "model_versions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "predictions" (
    "id" SERIAL NOT NULL,
    "model_version_id" INTEGER NOT NULL,
    "for_date" DATE,
    "items" JSONB NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "predictions_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "draws_date_key" ON "draws"("date");

-- CreateIndex
CREATE INDEX "draws_date_idx" ON "draws"("date");

-- CreateIndex
CREATE INDEX "predictions_for_date_idx" ON "predictions"("for_date");

-- AddForeignKey
ALTER TABLE "predictions" ADD CONSTRAINT "predictions_model_version_id_fkey" FOREIGN KEY ("model_version_id") REFERENCES "model_versions"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
