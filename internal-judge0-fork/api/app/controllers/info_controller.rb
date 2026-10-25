class InfoController < ApplicationController
  def about
    render json: {name: "TechniView Python Runner", version: ENV.fetch("JUDGE0_VERSION")}
  end
end
