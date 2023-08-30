// Credits https://stackoverflow.com/a/34890276
var groupBy = function(xs, key) {
  return xs.reduce(function(rv, x) {
    (rv[x[key]] = rv[x[key]] || []).push(x);
    return rv;
  }, {});
};

let choices = null
let chart = null

function check() {
  if(choices == null) {
     window.setTimeout(check, 100); /* this checks the flag every 100 milliseconds*/
  } else {
    setup();
  }
}

var setup = (function() {
  var executed = false;
  return function() {
    if (executed) { return }
    if (choices == null) { return }
    executed = true;

    let ctx = document.getElementById('aggregate');
    Chart.defaults.color = '#FFF';
    chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: Object.entries(choices).map(arr => arr[1]).map(c => `${c.marker}/${c.choice}`),
        datasets: [{
          data: Object.entries(choices).map(arr => arr[1]).map(c => c.count),
          borderWidth: 1
        }]
      },
      options: {
        scales: {
          y: {
            beginAtZero: true
          },
          x: {
            ticks: {
              font: {
                size: 20
              }
            }
          }
        },
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          }
        }
      }
    });
  };
})();

function updateChart(status) {
  if (chart == null) {
    return;
  }

  chart.data.datasets[0].data = Object.entries(choices).map(arr => arr[1]).map(c => +c.count);
  chart.config.data.labels = Object.entries(choices).map(arr => arr[1]).map(c => `${c.marker}/${c.choice}`);
  chart.update();

}

function fetchPollResult() {
  $.get("/polls/display", function(json_data) {

    const get_data = function() {
      if ($.isEmptyObject(json_data)) { return false; }

      const data = json_data;
      const question = data.question;
      const anonymous = data.anonymous;
      const multiple_choice = data.multiple_choice;
      const status = data.status;
      const ungrouped_votes = data.votes;

      if (anonymous) {
        choices = Object.fromEntries(
          data.choices.map(
            e => [e.choice_id, {choice: e.choice, marker: e.marker, count: 0}]
          )
        )
      } else {
        if(status == 1) {
          choices = Object.fromEntries(
            [...data.choices.map(
              e => [e.choice_id, {choice: e.choice, marker: e.marker, count: 0}]
              ),
              [null, {choice: "Pending", marker: "⏳", count: 0}]
            ]
          )
        } else {
          choices = Object.fromEntries(
            [...data.choices.map(
              e => [e.choice_id, {choice: e.choice, marker: e.marker, count: 0}]
              ),
              [null, {choice: "Pending", marker: "", count: 0}]
            ]
          )
        }
      }


      // group votes by the team code
      $("#question").text(question);
      $("#anonymous").text(anonymous ? 'Yes' : 'No');
      $("#multiple-choice").text(multiple_choice ? 'Yes' : 'No');
      $("#status").html(DOMPurify.sanitize(`<span class="fw-bold text-${['info', 'success', 'warning'][status]}">${['Inactive', 'Active', 'closed'][status]}</span>`));
      if (anonymous) {
        ungrouped_votes.forEach(vote => {
          choices[vote.choice_id].count += vote.count;
        });

        $('#result').html('');
      } else {
        ungrouped_votes.forEach(vote => {
          choices[vote.choice_id].count += 1;
        });

        const votes = groupBy(ungrouped_votes, 'team_code');
        $('#result').html(DOMPurify.sanitize(
          Object.entries(votes).map(([team_code, votes_by_team]) => (` 
                    <div class="col-12 col-sm-6 col-md-4 col-lg-3 col-xl-2 text-nowrap text-truncate">
                    ${
                      votes_by_team.map(vote => `<span title="${vote.voted_at ?? "pending"} / ${vote.voted_by ?? "pending"}">${choices[vote.choice_id].marker}</span>`).join('')
                    } 
                      &emsp; <span title="${team_code}">${team_code}</span>
                    </div>
                  `)).join('')
        ))
      }

      if (!anonymous && status != 1) {
        delete choices.null;
      }

      updateChart(status);

      return true;
    };
    
    const success = get_data();

    if (success) {
      $('#poll-exists').show();
      $('#no-poll').hide();
      setup()
    } else {
      $('#poll-exists').hide();
      $('#no-poll').show();
    }

    setTimeout(function () {
      fetchPollResult();
    }, 3000); 
  });
}
