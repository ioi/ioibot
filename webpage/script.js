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


function setup() {
  let ctx = document.getElementById('aggregate');
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
}

function updateChart() {
  if (chart == null) {
    return;
  }

  chart.data.datasets[0].data = Object.entries(choices).map(arr => arr[1]).map(c => c.count);
  chart.labels = Object.entries(choices).map(arr => arr[1]).map(c => `${c.marker}/${c.choice}`);
  chart.update();

}

function fetchPollResult() {
  $.get("/polls/display", function(json_data) {

    const data = json_data;
    const question = data.question;
    choices = Object.fromEntries(
      [...data.choices.map(
        e => [e.choice_id, {choice: e.choice, marker: e.marker, count: 0}]
        ),
        [null, {choice: "Pending", marker: "⏳", count: 0}]
      ]
    )


    window.choices = choices
    const anonymous = data.anonymous;
    const multiple_choice = data.multiple_choice;
    const status = data.status;
    const ungrouped_votes = data.votes;
    
    // group votes by the team code
    $("#question").text(question);
    $("#anonymous").text(anonymous ? 'Yes' : 'No');
    $("#multiple-choice").text(multiple_choice ? 'Yes' : 'No');
    $("#status").html(DOMPurify.sanitize(`<span class="fw-bold text-${['info', 'success', 'warning'][status]}">${['Inactive', 'Active', 'closed'][status]}</span>`));
    if (anonymous) {
    
    } else {
      ungrouped_votes.forEach(vote => {
        choices[vote.choice_id].count += 1;
      });
      updateChart();

      const votes = groupBy(ungrouped_votes, 'team_code');
      $('#result').html(DOMPurify.sanitize(
        Object.entries(votes).map(([team_code, votes_by_team]) => {
          return (` 
              <div class="col-12 col-sm-6 col-md-4 col-lg-3 col-xl-2 text-nowrap text-truncate">
              ${
                votes_by_team.map(vote => `<span title="${vote.voted_at ?? "pending"} / ${vote.voted_by ?? "pending"}">${choices[vote.choice_id].marker}</span>`).join('')
              } 
                &emsp; <span title="${team_code}">${team_code}</span>
              </div>
            `);
          }).join('')
      ))
    }

    setTimeout(function () {
      fetchPollResult(data);
    }, 3000); 
  });
}
