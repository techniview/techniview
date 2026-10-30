class SubmissionsController < ApplicationController
  before_action :check_maintenance, only: :create
  before_action :set_response_options

  INPUT_FIELDS = %i[source_code stdin expected_output number_of_runs cpu_time_limit
                    cpu_extra_time wall_time_limit memory_limit stack_limit
                    max_processes_and_or_threads max_file_size redirect_stderr_to_stdout
                    callback_url].freeze
  UNSUPPORTED_FIELDS = %w[language_id additional_files compiler_options command_line_arguments
                          enable_network enable_per_process_and_thread_time_limit
                          enable_per_process_and_thread_memory_limit].freeze

  def show
    render json: Submission.find_by!(token: params[:token]),
           base64_encoded: @base64_encoded, fields: @requested_fields
  rescue Encoding::UndefinedConversionError
    render json: {error: "output requires base64_encoded=true"}, status: :bad_request
  end

  def create
    unsupported = UNSUPPORTED_FIELDS & params.keys
    if unsupported.any?
      render json: {error: "unsupported fields", fields: unsupported}, status: :unprocessable_entity
      return
    end
    if params[:wait] == "true" && !Config::ENABLE_WAIT_RESULT
      render json: {error: "wait not allowed"}, status: :bad_request
      return
    end
    if Resque.size(ENV.fetch("JUDGE0_VERSION")) >= Config::MAX_QUEUE_SIZE
      render json: {error: "queue is full"}, status: :service_unavailable
      return
    end

    attributes = params.permit(*INPUT_FIELDS).to_h
    if @base64_encoded
      %w[source_code stdin expected_output].each do |field|
        attributes[field] = Base64Service.decode(attributes[field])
      end
    end
    attributes[:language_id] = Language.where(is_archived: false).first!.id
    submission = Submission.new(attributes)
    unless submission.save
      render json: submission.errors, status: :unprocessable_entity
      return
    end

    if params[:wait] == "true"
      ExecutionRunner.perform_now(submission)
      render json: submission.reload, status: :created,
             base64_encoded: @base64_encoded, fields: @requested_fields
    else
      ExecutionRunner.perform_later(submission)
      render json: {token: submission.token}, status: :created
    end
  rescue Encoding::UndefinedConversionError
    render json: {error: "output requires base64_encoded=true", token: submission.token},
           status: :created
  end

  private

  def set_response_options
    fields = Fields::Submission.new(params[:fields])
    if fields.has_invalid_fields?
      render json: {error: "invalid fields", fields: fields.invalid_fields}, status: :bad_request
      return
    end
    @requested_fields = fields.requested_fields
    @base64_encoded = params[:base64_encoded] != "false"
  end
end
