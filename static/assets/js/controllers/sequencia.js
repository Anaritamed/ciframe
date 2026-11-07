angular.module('deciframeApp').controller('SequenciaController', function($http, $window, ngProgressFactory, $anchorScroll, $location, GENEROS) {
  var vm = this;
  vm.sequenciasFamosas = [];
  vm.minhaSequencia = {};
  vm.isSearching = false;
  vm.showSearchResultsCount = false;
  vm.esfigeSpeech =  "";
  vm.musics = [];
  vm.generos = GENEROS;
  vm.meuGenero = "";
  vm.progressbar = ngProgressFactory.createInstance();
  vm.novaSequencia = { name: '', chords: '' };
  vm.formError = '';
  vm.isSubmitting = false;

  var COR = '#2E1C74';

  var toViewModel = function(sequencia) {
    return {
      id: sequencia.id,
      slug: sequencia.slug,
      name: sequencia.name,
      match_mode: sequencia.match_mode,
      legacy_id: sequencia.legacy_id,
      acordes: (sequencia.chords || []).map(function(acorde) {
        return { 'acorde': acorde, 'cor': COR };
      })
    };
  };

  var carregarSequencias = function(callback) {
    $http.get('sequencias')
      .success(function(data) {
        vm.sequenciasFamosas = data.map(toViewModel);
        if (callback) {
          callback();
        }
      })
      .error(function() {
        vm.formError = 'Não foi possível carregar o catálogo de sequências.';
      });
  };

  vm.temAcorde = function(acorde) {
    if (vm.minhaSequencia && vm.minhaSequencia.acordes) {
      return (vm.minhaSequencia.acordes.indexOf(acorde) > -1);
    } else {
      return false;
    }
  }

  var createChordsString = function(chords) {
    var str = "";
    for (var i = 0; i < chords.length; i++) {
      str = str.concat(chords[i].acorde, ',');
    }
    return str.substring(0, str.length-1);
  }

  var sequenciaIdent = function(sequencia) {
    if (sequencia.slug) {
      return sequencia.slug;
    }
    return createChordsString(sequencia.acordes || []);
  }

  vm.pesquisarPorSequencia = function(sequencia) {
    if (sequencia) {
      vm.minhaSequencia = sequencia;
    }
    if (!vm.minhaSequencia || !vm.minhaSequencia.acordes ||
        !vm.minhaSequencia.acordes.length) {
      return;
    }

    vm.progressbar.start();
    vm.esfigeSpeech = "Procurando músicas com base na sequencia...";
    vm.isSearching = true;
    vm.musics = [];

    var searchString = "similares?sequencia=" + encodeURIComponent(sequenciaIdent(vm.minhaSequencia));
    if (vm.meuGenero !== "" && vm.meuGenero !== null) {
      searchString += "&generos=" + encodeURIComponent(vm.meuGenero);
    }
    $http.get(searchString)
      .success(function(data) {
        vm.progressbar.complete();
        vm.esfigeSpeech = "Encontrei essas músicas";
        vm.isSearching = false;
        vm.showSearchResultsCount = true;
        vm.musics = data;
      })
      .error(function(data) {
        vm.progressbar.complete();
        vm.esfigeSpeech = "Ops! Algo errado.";
        vm.isSearching = false;
        vm.showSearchResultsCount = false;
      });
  }

  vm.cadastrarSequencia = function() {
    vm.formError = '';
    var name = (vm.novaSequencia.name || '').trim();
    var rawChords = (vm.novaSequencia.chords || '').trim();

    if (!name) {
      vm.formError = 'Informe um nome para a sequência.';
      return;
    }
    if (!rawChords) {
      vm.formError = 'Informe ao menos um acorde.';
      return;
    }

    var chords = rawChords.split(',').map(function(acorde) {
      return acorde.trim();
    }).filter(function(acorde) {
      return acorde.length > 0;
    });

    if (!chords.length) {
      vm.formError = 'Informe ao menos um acorde.';
      return;
    }

    vm.isSubmitting = true;
    $http.post('sequencias', { name: name, chords: chords })
      .success(function(data) {
        vm.isSubmitting = false;
        vm.novaSequencia = { name: '', chords: '' };
        carregarSequencias(function() {
          for (var i = 0; i < vm.sequenciasFamosas.length; i++) {
            if (vm.sequenciasFamosas[i].id === data.id) {
              vm.minhaSequencia = vm.sequenciasFamosas[i];
              vm.pesquisarPorSequencia();
              break;
            }
          }
        });
      })
      .error(function(data) {
        vm.isSubmitting = false;
        vm.formError = (data && data.error) ? data.error : 'Não foi possível cadastrar a sequência.';
      });
  }

  vm.limparPesquisa = function() {
    vm.minhaSequencia = {};
    vm.musics = [];
  }

  vm.goToLirics = function(music) {
    $window.open(music.url);
  };

  vm.goToResults = function() {
    vm.showSearchResultsCount = false;
    $("body").animate({scrollTop: $("#results").offset().top}, "slow");
  };

  carregarSequencias();
});
