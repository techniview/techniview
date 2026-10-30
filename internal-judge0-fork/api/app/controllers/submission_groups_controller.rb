require "digest"

class SubmissionGroupsController < ApplicationController
  CASE_FIELDS = (SubmissionsController::INPUT_FIELDS - [:number_of_runs]).map(&:to_s).freeze

  def create
    key = params[:idempotency_key].to_s
    cases = params[:cases]
    unless key.match?(/\A[a-zA-Z0-9_-]{16,128}\z/) && cases.is_a?(Array) &&
           cases.any? && cases.size <= 256
      return render json: {error: "invalid group request"}, status: :unprocessable_entity
    end
    prepared = cases.map do |item|
      fields = item.to_unsafe_h
      allowed = CASE_FIELDS + ["case_id"]
      unless fields.keys.sort == (fields.keys & allowed).sort &&
             fields["case_id"].to_s.match?(/\A[1-9][0-9]*\z/)
        return render json: {error: "invalid case"}, status: :unprocessable_entity
      end
      fields
    end
    ids = prepared.map { |item| item.fetch("case_id").to_i }
    if ids.uniq.size != ids.size
      return render json: {error: "duplicate case id"}, status: :unprocessable_entity
    end
    digest = Digest::SHA256.hexdigest(JSON.generate(prepared))
    existing = SubmissionGroup.find_by(idempotency_key: key)
    if existing
      return render_existing(existing, digest)
    end
    group = nil
    SubmissionGroup.transaction do
      group = SubmissionGroup.create!(token: SecureRandom.uuid, idempotency_key: key,
                                      payload_sha256: digest)
      language_id = Language.where(is_archived: false).first!.id
      prepared.each_with_index do |item, position|
        attributes = item.except("case_id")
        attributes["language_id"] = language_id
        attributes["number_of_runs"] = 1
        submission = Submission.create!(attributes)
        group.group_cases.create!(submission: submission, case_id: ids.fetch(position),
                                  position: position)
      end
    end
    SubmissionGroup.publish_due
    render_group(group, :created)
  rescue ActiveRecord::RecordNotUnique
    render_existing(SubmissionGroup.find_by!(idempotency_key: key), digest)
  rescue ActiveRecord::RecordInvalid => error
    render json: {error: error.record.errors.full_messages}, status: :unprocessable_entity
  end

  def show
    render_group(SubmissionGroup.find_by!(token: params[:token]))
  end

  def by_key
    render_group(SubmissionGroup.find_by!(idempotency_key: params[:key]))
  end

  private

  def render_existing(group, digest)
    return render json: {error: "idempotency key conflict"}, status: :conflict if group.payload_sha256 != digest
    SubmissionGroup.publish_due
    render_group(group)
  end

  def render_group(group, status = :ok)
    render json: {
      token: group.token,
      state: group.state,
      cases: group.group_cases.includes(:submission).order(:position).map do |item|
        {case_id: item.case_id, token: item.submission.token, state: item.state}
      end
    }, status: status
  end
end
