function fetchPollResult() {
	$.get("./polls/active", function(data) {
		refreshPoll(data);
		refreshCounter(data);

		setTimeout(function () {
			fetchPollResult(data);
		}, 3000); 
	});
}

function refreshPoll(data) {
	$(".countryVote").remove();
	$("#guide").empty();
	if(Object.keys(data).length === 0) {
		$("#question").html("No poll is currently active.")
		return;
	}

	$("#question").html(data.question);
	$("#guide").html('Cast your vote by sending "vote" to @ioibot');

	const imgLink = {
		"yes"     : "./webpage/asset/yes.png",
		"no"      : "./webpage/asset/no.png",
		"abstain" : "./webpage/asset/abstain.png",
		null      : "./webpage/asset/empty.png"
	};

	var column = 10;
	var index = 0;
	var $result = $("#result");
	for(var key in data.votes) {
		if(!data.votes.hasOwnProperty(key)) {
			continue;
		}

		var img = '<img class="align-self-center mr-3 choice" src="' + 
		           imgLink[data.votes[key]] + '">';

		key = key.toUpperCase()
		var country = '<div class="align-self-center media-body country"><span>' 
		              + key + '</span></div>';

		var $countryVote = $('<div class="media countryVote"></div>');
		$countryVote.append(img);
		$countryVote.append(country)
		$result.append($countryVote);
	}
}

function refreshCounter(data) {
	counter = {
		"yes"     : 0,
		"no"      : 0,
		"abstain" : 0,
		null	  : 0
	};

	statement = {
		"yes"     : "Yes",
		"no"      : "No",
		"abstain" : "Abstain",
		null      : "none"
	};

	for(var key in data.votes) {
		if(!data.votes.hasOwnProperty(key)) {
			continue;
		}
		counter[data.votes[key]]++;
	}

	var yesPerc = 0;
	var noPerc = 0;
	if(counter["yes"] + counter["no"] > 0) {
		yesPerc = 100 * counter["yes"] / (counter["yes"] + counter["no"]);
		noPerc = 100 - yesPerc;

		yesPerc = yesPerc.toFixed(2);
		noPerc = noPerc.toFixed(2);
	}

	for(var key in counter) {
		var elementID = `#${key}Count`;
		var text = `${statement[key]} : ${counter[key]}`;
		if(key == "yes") {
			text += ` (${yesPerc}%)`
		}
		else if(key == "no") {
			text += ` (${noPerc}%)`
		}

		$(elementID).html(text);
	}
}

function roundDec(num, dec) {
	return Number(Math.round(num + "e" + dec) + "e-" + dec)
}