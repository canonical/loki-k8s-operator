Feature: Inject extra labels to alert rules

  Scenario: Extra labels are appended to all rules
    Given rules
      """
      groups:
        - rules:
            - labels:
                severity: critical
            - labels:
                severity: warning
      """
    When extra labels are injected
      """
      environment: production
      team: observability
      """
    Then modified rules match
      """
      groups:
        - rules:
            - labels:
                severity: critical
                environment: production
                team: observability
            - labels:
                severity: warning
                environment: production
                team: observability
      """

  Scenario: Extra labels override existing labels with the same key
    Given rules
      """
      groups:
        - rules:
            - labels:
                severity: warning
                team: old-team
      """
    When extra labels are injected
      """
      team: new-team
      """
    Then modified rules match
      """
      groups:
        - rules:
            - labels:
                severity: warning
                team: new-team
      """

  Scenario: Empty extra labels leaves rules unchanged
    Given rules
      """
      groups:
        - rules:
            - labels:
                severity: warning
                team: some-team
      """
    When extra labels are injected
      """
      """
    Then modified rules match
      """
      groups:
        - rules:
            - labels:
                severity: warning
                team: some-team
      """

  Scenario: Rules without a labels key get labels added
    Given rules
      """
      groups:
        - rules:
            - alert: NoLabelsAlert
      """
    When extra labels are injected
      """
      env: staging
      """
    Then modified rules match
      """
      groups:
        - rules:
            - alert: NoLabelsAlert
              labels:
                env: staging
      """

  Scenario: Empty label values removes the label
    Given rules
      """
      groups:
        - rules:
            - name: first
              labels:
                env: env1
            - name: second
              labels:
                env: env2
                foo: bar
                severity: warning
      """
    When extra labels are injected
      """
      env: null
      foo: ""
      """
    Then modified rules match
      """
      groups:
        - rules:
            - name: first
            - name: second
              labels:
                severity: warning
      """
