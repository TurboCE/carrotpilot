# GM manual auto hold

Supported with camera longitudinal control on the Traverse (SDGM harness), Trailblazer (regular ACC) and Trax. Enable the device's `AlphaLongitudinalEnabled` toggle. Cruise-only models and gas-interceptor configurations are excluded. There is no separate auto-hold toggle.

With both openpilot and stock cruise disengaged, press the brake firmly at low speed in D/L and come to a complete stop. The strong-press threshold is 80 raw pedal units, not 80 percent. Arming is possible below 1.5 m/s, but a hold command is issued only while stopped. The initial release retains the hold; a subsequent light brake press and release cancels it.

Acceleration, engagement, parking brake, shifting out of D/L, movement, CAN faults or stale inputs clear the hold. The Trailblazer also requires fresh stock-camera command references. Automatic SET/RES button commands are suppressed during a hold.

Panda safety firmware supporting this feature is required. A branch update does not mean installation or vehicle braking validation. The feature has not been validated to guarantee sufficient braking on slopes.

[Settings catalog](settings.md)
